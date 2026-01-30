from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .currency import convert_to_rub
from .models import Subscription, User
from .schemas import SubscriptionCreate, UserCreate, SubscriptionUpdate
from .security import get_password_hash

# Subscription CRUD operations
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

def get_user_subscriptions(db: Session, user_id: int):
    query = select(Subscription).where(Subscription.user_id == user_id)
    return db.execute(query).scalars().all()

def get_user_subscriptions_by_category(db: Session, user_id: int, category: str):
    query = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.category == category
    )
    return db.execute(query).scalars().all()

def update_subscription(db: Session, sub_id: int, user_id: int, update_data: SubscriptionUpdate):
    query = select(Subscription).where(
        Subscription.id == sub_id, 
        Subscription.user_id == user_id
    )
    db_sub = db.execute(query).scalar_one_or_none()
    
    if db_sub:
        obj_data = update_data.model_dump(exclude_unset=True)
        for key, value in obj_data.items():
            setattr(db_sub, key, value)
        
        db.commit()
        db.refresh(db_sub)
        return db_sub
    
    return None

def get_category_average(db: Session, category: str, rates: dict):
    query = select(Subscription).where(Subscription.category == category)
    subs = db.execute(query).scalars().all()

    if not subs:
        return 0.0

    total_sum = 0.0
    for sub in subs:
        price_in_rub = convert_to_rub(sub.price, sub.currency, rates)
        total_sum += price_in_rub

    return round(total_sum / len(subs), 2)

def delete_subscription(db: Session, sub_id: int, user_id: int):
    query = select(Subscription).where(
        Subscription.id == sub_id, 
        Subscription.user_id == user_id
    )
    db_sub = db.execute(query).scalar_one_or_none()
    
    if db_sub:
        db.delete(db_sub)
        db.commit()
        return db_sub
    return None

def get_user_total_subscription_cost(db: Session, user_id: int):
    query = select(func.sum(Subscription.price)).where(Subscription.user_id == user_id)
    total_cost = db.execute(query).scalar()
    return total_cost or 0.0

def get_user_expenses_by_all_categories(db: Session, user_id: int):
    query = (
        select(
            Subscription.category, 
            func.sum(Subscription.price).label("total")
        )
        .where(Subscription.user_id == user_id)
        .group_by(Subscription.category)
    )
    result = db.execute(query).all()
    
    return [{"category": row[0], "category_sum": row[1]} for row in result]

# User CRUD operations
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

def get_user_by_email(db: Session, email: str):
    query = select(User).where(User.email == email)
    return db.execute(query).scalar_one_or_none()

def get_user_by_nickname(db: Session, name: str):
    query = select(User).where(User.name == name)
    return db.execute(query).scalar_one_or_none()