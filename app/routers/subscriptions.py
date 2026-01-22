from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import schemas, crud, security, models

router = APIRouter(prefix="/subs", tags=["subscriptions"])

@router.post("/", response_model=schemas.SubscriptionRead)
def create_subscription(
    subscription: schemas.SubscriptionCreate,
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return crud.create_subscription(db=db, subscription=subscription, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.SubscriptionRead])
def read_user_subscriptions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user)
):
    try:
        return crud.get_user_subscriptions(db=db, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))