from sqlalchemy.orm import Session
from .models import Subscription, User
from .schemas import SubscriptionCreate, UserCreate
from .security import get_password_hash

def create_subscription(
    db: Session, 
    subscription: SubscriptionCreate, 
    user_id: int,
):
    db_subscription = Subscription(
        **subscription.model_dump(), 
        user_id=user_id
    )
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription

def get_user_subscriptions(
    db: Session,
    user_id: int
):
    return db.query(Subscription).filter(Subscription.user_id == user_id).all()

def delete_subscription(
    db: Session, 
    sub_id: int
):
    db_sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    if db_sub:
        db.delete(db_sub)
        db.commit()
    return db_sub

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_name(db: Session, name: str):
    return db.query(User).filter(User.name == name).first()

def create_user(db: Session, user: UserCreate):
    hashed_password = get_password_hash(user.password)
    
    db_user = User(
        email=user.email, 
        hashed_password=hashed_password,
        name=user.name
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user