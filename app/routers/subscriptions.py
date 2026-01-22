from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import schemas, crud

router = APIRouter(prefix="/subs", tags=["subscriptions"])

@router.post("/", response_model=schemas.SubscriptionRead)
def create_subscription(
    subscription: schemas.SubscriptionCreate,
    db: Session = Depends(get_db)
):
    try:
        return crud.create_subscription(db=db, subscription=subscription, user_id=1)  # Временно user_id захардкожен
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.SubscriptionRead])
def read_user_subscriptions(
    db: Session = Depends(get_db)
):
    try:
        return crud.get_user_subscriptions(db=db, user_id=1)  # Временно user_id захардкожен
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))