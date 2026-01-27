from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated, List
from ..database import get_db
from ..currency import get_rates, convert_to_rub
from .. import schemas, models, crud, security

router = APIRouter(prefix="/subs", tags=["subscriptions"])

CurUser = Annotated[models.User, Depends(security.get_current_user)]
DBSession = Annotated[Session, Depends(get_db)]
Rates = Annotated[dict, Depends(get_rates)]

@router.post("/", response_model=schemas.SubscriptionRead)
def create_subscription(
    subscription: schemas.SubscriptionCreate,
    current_user: CurUser,
    db: DBSession
):
    try:
        return crud.create_subscription(db=db, subscription=subscription, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.SubscriptionRead])
async def read_subscriptions(
    db: DBSession,
    current_user: CurUser,
    rates: Rates
):
    subs = crud.get_user_subscriptions(db=db, user_id=current_user.id)
    
    for sub in subs:
        sub.price_rub = convert_to_rub(sub.price, sub.currency, rates)
        
    return subs

@router.get("/report", response_model=schemas.AllCategoriesReport)
async def get_full_expenses_report(
    db: DBSession,
    current_user: CurUser,
    rates: Rates
):
    
    subs = crud.get_user_subscriptions(db=db, user_id=current_user.id)
    
    report_dict = {}
    total_monthly = 0.0
    
    for sub in subs:
        price_in_rub = convert_to_rub(sub.price, sub.currency, rates)
        total_monthly += price_in_rub
        
        if sub.category in report_dict:
            report_dict[sub.category] += price_in_rub
        else:
            report_dict[sub.category] = price_in_rub
    
    categories_stats = [
        {"category": cat, "category_sum": round(val, 2)} 
        for cat, val in report_dict.items()
    ]
    
    return {
        "total_monthly": round(total_monthly, 2),
        "categories": categories_stats
    }
    
@router.get("/report/{category}", response_model=schemas.CategoryReport)
async def get_category_expenses_report(
    category: str,
    db: DBSession,
    current_user: CurUser,
    rates: Rates
):
    subs = crud.get_user_subscriptions(db=db, user_id=current_user.id)
    
    filtered_subs = []
    total_monthly = 0.0
    
    for sub in subs:
        if sub.category == category:
            sub.price_rub = convert_to_rub(sub.price, sub.currency, rates)
            total_monthly += sub.price_rub
            filtered_subs.append(sub)
    
    return {
        "category": category,
        "services": filtered_subs,
        "total_monthly": round(total_monthly, 2)
    }

@router.delete("/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: int,
    db: DBSession,
    current_user: CurUser
):
    db_sub = crud.delete_subscription(db=db, sub_id=sub_id, user_id=current_user.id)
    
    if not db_sub:
        raise HTTPException(status_code=404, detail="Subscription not found or access denied")
    
    return None