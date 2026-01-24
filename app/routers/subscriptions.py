from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated, List
from ..database import get_db
from .. import schemas, models, crud, security

router = APIRouter(prefix="/subs", tags=["subscriptions"])

CurUser = Annotated[models.User, Depends(security.get_current_user)]
DBSession = Annotated[Session, Depends(get_db)]

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
def read_user_subscriptions(
    db: DBSession,
    current_user: CurUser
):
    try:
        return crud.get_user_subscriptions(db=db, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get("/total_expenses", response_model=float)
def get_user_total_subscription_cost(
    db: DBSession,
    current_user: CurUser
):
    try:
        return crud.get_user_total_subscription_cost(db=db, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{sub_id}", response_model=schemas.SubscriptionDelete)
def delete_subscription(
    sub_id: int,
    db: DBSession,
    current_user: CurUser
):
    db_sub = crud.delete_subscription(db=db, sub_id=sub_id, user_id=current_user.id)
    
    if db_sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found or access denied")
    
    return db_sub