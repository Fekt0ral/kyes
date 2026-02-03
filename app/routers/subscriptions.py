from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Annotated, List
from ..database import get_db
from ..currency import get_rates, convert_price
from ..logger import get_logger
from .. import schemas, models, crud, security

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
logger = get_logger(__name__)

CurUser = Annotated[models.User, Depends(security.get_current_user)]
DBSession = Annotated[Session, Depends(get_db)]
Rates = Annotated[dict, Depends(get_rates)]

@router.post("/", response_model=schemas.SubscriptionRead, status_code=201)
def create_subscription(
    subscription: schemas.SubscriptionCreate,
    current_user: CurUser,
    db: DBSession,
    rates: Rates,
    force: bool = Query(False, description="Force creation even if subscription already exists")
):
    existing = crud.check_subscription_exists(
        db=db, 
        user_id=current_user.id, 
        service_name=subscription.service_name
    )
    
    if existing and not force:
        preferred_currency = current_user.preferred_currency or "RUB"
        for sub in existing:
            sub.display_price = convert_price(sub.price, sub.currency, preferred_currency, rates)
            sub.display_currency = preferred_currency

        logger.info(
            "Попытка создать дубликат подписки",
            extra={"user_id": current_user.id, "service_name": subscription.service_name}
        )
        
        warning_response = schemas.DuplicateWarning(
            warning="duplicate_subscription",
            message=f"Subscription '{subscription.service_name}' already exists. Use force=true to create anyway.",
            existing_subscriptions=existing
        )
        
        raise HTTPException(
            status_code=409,
            detail=warning_response.model_dump(mode="json")
        )
    
    try:
        db_sub = crud.create_subscription(db=db, subscription=subscription, user_id=current_user.id)
        preferred_currency = current_user.preferred_currency or "RUB"
        db_sub.display_price = convert_price(db_sub.price, db_sub.currency, preferred_currency, rates)
        db_sub.display_currency = preferred_currency
        logger.info(
            "Подписка создана",
            extra={"user_id": current_user.id, "sub_id": db_sub.id, "service_name": db_sub.service_name}
        )
        return db_sub
    
    except Exception as e:
        logger.exception(
            "Ошибка создания подписки",
            extra={"user_id": current_user.id, "service_name": subscription.service_name}
        )
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.SubscriptionRead])
async def read_subscriptions(
    db: DBSession,
    current_user: CurUser,
    rates: Rates
):
    subs = crud.get_user_subscriptions(db=db, user_id=current_user.id)
    preferred_currency = current_user.preferred_currency or "RUB"
    
    for sub in subs:
        sub.display_price = convert_price(sub.price, sub.currency, preferred_currency, rates)
        sub.display_currency = preferred_currency
        
    subs = sorted(subs, key=lambda x: x.display_price, reverse=True)
    logger.info("Запрошен список подписок", extra={"user_id": current_user.id, "count": len(subs)})
        
    return subs

@router.get("/reports/summary", response_model=schemas.AllCategoriesReport)
async def get_full_expenses_report(
    db: DBSession,
    current_user: CurUser,
    rates: Rates
):
    
    subs = crud.get_user_subscriptions(db=db, user_id=current_user.id)
    preferred_currency = current_user.preferred_currency or "RUB"
    
    report_dict = {}
    total_monthly = 0.0
    
    for sub in subs:
        price_converted = convert_price(sub.price, sub.currency, preferred_currency, rates)
        total_monthly += price_converted
        
        if sub.category in report_dict:
            report_dict[sub.category] += price_converted
        else:
            report_dict[sub.category] = price_converted
            
    report_dict = sorted(report_dict.items(), key=lambda item: item[1], reverse=True)
    
    categories_stats = [
        {"category": cat, "category_sum": round(val, 2)} 
        for cat, val in report_dict
    ]
    
    logger.info(
        "Сформирован общий отчет по категориям",
        extra={"user_id": current_user.id, "categories": len(categories_stats)}
    )
    return {
        "currency": preferred_currency,
        "total_monthly": round(total_monthly, 2),
        "categories": categories_stats
    }
    
@router.get("/reports/{category}", response_model=schemas.CategoryReport)
async def get_category_expenses_report(
    category: str,
    db: DBSession,
    current_user: CurUser,
    rates: Rates
):
    subs = crud.get_user_subscriptions_by_category(db=db, user_id=current_user.id, category=category)
    preferred_currency = current_user.preferred_currency or "RUB"
    
    total_monthly = 0.0
    
    for sub in subs:
        sub.display_price = convert_price(sub.price, sub.currency, preferred_currency, rates)
        sub.display_currency = preferred_currency
        total_monthly += sub.display_price
    
    logger.info(
        "Сформирован отчет по категории",
        extra={"user_id": current_user.id, "category": category, "count": len(subs)}
    )
    return {
        "category": category,
        "currency": preferred_currency,
        "services": subs,
        "total_monthly": round(total_monthly, 2)
    }
    
@router.get("/average/{category}")
def get_average_by_category(
    category: str,
    db: DBSession,
    rates: Rates,
    current_user: CurUser # Оставляем авторизацию, чтобы только авторизованные пользователи могли делать запросы
):
    preferred_currency = current_user.preferred_currency or "RUB"
    avg_price = crud.get_category_average(db, category, rates, preferred_currency)
    
    logger.info(
        "Запрошена средняя стоимость по категории",
        extra={"user_id": current_user.id, "category": category}
    )
    return {
        "category": category,
        "average_price": avg_price,
        "currency": preferred_currency
    }

@router.patch("/update/{sub_id}", response_model=schemas.SubscriptionRead)
def update_subscription_route(
    sub_id: int,
    update_data: schemas.SubscriptionUpdate,
    db: DBSession,
    current_user: CurUser,
    rates: Rates
):
    db_sub = crud.update_subscription(
        db=db, 
        sub_id=sub_id, 
        user_id=current_user.id, 
        update_data=update_data
    )
    
    if not db_sub:
        raise HTTPException(status_code=404, detail="Subscription not found or access denied.")
    
    preferred_currency = current_user.preferred_currency or "RUB"
    db_sub.display_price = convert_price(db_sub.price, db_sub.currency, preferred_currency, rates)
    db_sub.display_currency = preferred_currency
    logger.info(
        "Подписка обновлена",
        extra={"user_id": current_user.id, "sub_id": db_sub.id}
    )
    return db_sub

@router.delete("/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: int,
    db: DBSession,
    current_user: CurUser
):
    db_sub = crud.delete_subscription(db=db, sub_id=sub_id, user_id=current_user.id)
    
    if not db_sub:
        raise HTTPException(status_code=404, detail="Subscription not found or access denied")
    
    logger.info(
        "Подписка удалена",
        extra={"user_id": current_user.id, "sub_id": sub_id}
    )
    return None