from sqlalchemy.orm import Session
from sqlalchemy import select, func, delete
from .currency import convert_price
from .models import Subscription, User, RefreshToken, SupportMessage, TelegramLinkToken
from .schemas import SubscriptionCreate, UserCreate, SubscriptionUpdate
from .security import get_password_hash

# Subscription CRUD operations
def create_subscription(
    db: Session, 
    subscription: SubscriptionCreate, 
    user_id: int,
):
    try:
        db_subscription = Subscription(
            **subscription.model_dump(), 
            user_id=user_id
        )
        db.add(db_subscription)
        db.commit()
        db.refresh(db_subscription)
        return db_subscription
    except Exception:
        db.rollback()
        raise

def get_user_subscriptions(db: Session, user_id: int):
    query = select(Subscription).where(Subscription.user_id == user_id)
    return db.execute(query).scalars().all()

def check_subscription_exists(db: Session, user_id: int, service_name: str):
    query = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.service_name == service_name
    )
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
        try:
            obj_data = update_data.model_dump(exclude_unset=True)
            for key, value in obj_data.items():
                setattr(db_sub, key, value)
            
            db.commit()
            db.refresh(db_sub)
            return db_sub
        except Exception:
            db.rollback()
            raise
    
    return None

def get_category_average(db: Session, category: str, rates: dict, target_currency: str):
    query = select(Subscription).where(Subscription.category == category)
    subs = db.execute(query).scalars().all()

    if not subs:
        return 0.0

    total_sum = 0.0
    for sub in subs:
        total_sum += convert_price(sub.price, sub.currency, target_currency, rates)

    return round(total_sum / len(subs), 2)

def delete_subscription(db: Session, sub_id: int, user_id: int):
    query = select(Subscription).where(
        Subscription.id == sub_id, 
        Subscription.user_id == user_id
    )
    db_sub = db.execute(query).scalar_one_or_none()
    
    if db_sub:
        try:
            db.delete(db_sub)
            db.commit()
            return db_sub
        except Exception:
            db.rollback()
            raise
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
def create_user(db: Session, user: UserCreate, email_verified: bool = True):
    try:
        hashed_password = get_password_hash(user.password)
        
        db_user = User(
            email=user.email, 
            hashed_password=hashed_password,
            name=user.name,
            preferred_currency=user.preferred_currency,
            email_verified=email_verified
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception:
        db.rollback()
        raise

def create_user_telegram(db: Session, name: str, password: str):
    try:
        hashed_password = get_password_hash(password)
        db_user = User(
            email=None,
            hashed_password=hashed_password,
            name=name,
            preferred_currency="RUB",
            email_verified=False
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception:
        db.rollback()
        raise

def update_user_preferred_currency(db: Session, user_id: int, preferred_currency: str):
    query = select(User).where(User.id == user_id)
    db_user = db.execute(query).scalar_one_or_none()
    if not db_user:
        return None
    try:
        db_user.preferred_currency = preferred_currency
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception:
        db.rollback()
        raise

def update_user_fields(
    db: Session,
    user_id: int,
    email: str = None,
    name: str = None,
    hashed_password: str = None,
    password_changed_at = None,
    last_email_change = None,
    last_name_change = None,
    last_password_change = None,
    email_verified: bool | None = None
):
    query = select(User).where(User.id == user_id)
    db_user = db.execute(query).scalar_one_or_none()
    if not db_user:
        return None
    try:
        if email is not None:
            db_user.email = email
        if name is not None:
            db_user.name = name
        if hashed_password is not None:
            db_user.hashed_password = hashed_password
        if password_changed_at is not None:
            db_user.password_changed_at = password_changed_at
        if last_email_change is not None:
            db_user.last_email_change = last_email_change
        if last_name_change is not None:
            db_user.last_name_change = last_name_change
        if last_password_change is not None:
            db_user.last_password_change = last_password_change
        if email_verified is not None:
            db_user.email_verified = email_verified
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception:
        db.rollback()
        raise

def get_user_by_email(db: Session, email: str):
    query = select(User).where(User.email == email)
    return db.execute(query).scalar_one_or_none()

def get_user_by_id(db: Session, user_id: int):
    query = select(User).where(User.id == user_id)
    return db.execute(query).scalar_one_or_none()

def get_user_by_telegram_id(db: Session, telegram_id: str):
    query = select(User).where(User.telegram_id == telegram_id)
    return db.execute(query).scalar_one_or_none()

def update_user_telegram(db: Session, user_id: int, telegram_id: str, telegram_chat_id: str):
    query = select(User).where(User.id == user_id)
    db_user = db.execute(query).scalar_one_or_none()
    if not db_user:
        return None
    try:
        db_user.telegram_id = telegram_id
        db_user.telegram_chat_id = telegram_chat_id
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception:
        db.rollback()
        raise

def create_refresh_token(db: Session, user_id: int, token_hash: str, expires_at):
    try:
        db_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db.add(db_token)
        db.commit()
        db.refresh(db_token)
        return db_token
    except Exception:
        db.rollback()
        raise

def get_refresh_token_by_hash(db: Session, token_hash: str):
    query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    return db.execute(query).scalar_one_or_none()

def revoke_refresh_token(db: Session, token: RefreshToken, revoked_at):
    try:
        token.revoked_at = revoked_at
        db.commit()
        db.refresh(token)
        return token
    except Exception:
        db.rollback()
        raise

def revoke_user_refresh_tokens(db: Session, user_id: int, revoked_at):
    try:
        query = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None)
        )
        tokens = db.execute(query).scalars().all()
        for token in tokens:
            token.revoked_at = revoked_at
        db.commit()
        return tokens
    except Exception:
        db.rollback()
        raise

def create_support_message(db: Session, user_id: int | None, message: str):
    try:
        db_msg = SupportMessage(user_id=user_id, message=message)
        db.add(db_msg)
        db.commit()
        db.refresh(db_msg)
        return db_msg
    except Exception:
        db.rollback()
        raise

def create_telegram_link_token(db: Session, user_id: int, token_hash: str, expires_at):
    try:
        db_token = TelegramLinkToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db.add(db_token)
        db.commit()
        db.refresh(db_token)
        return db_token
    except Exception:
        db.rollback()
        raise

def get_telegram_link_token_by_hash(db: Session, token_hash: str):
    query = select(TelegramLinkToken).where(TelegramLinkToken.token_hash == token_hash)
    return db.execute(query).scalar_one_or_none()

def mark_telegram_link_token_used(db: Session, token: TelegramLinkToken, used_at):
    try:
        token.used_at = used_at
        db.commit()
        db.refresh(token)
        return token
    except Exception:
        db.rollback()
        raise

def delete_user(db: Session, user_id: int):
    try:
        db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        db.execute(delete(TelegramLinkToken).where(TelegramLinkToken.user_id == user_id))
        db.execute(delete(SupportMessage).where(SupportMessage.user_id == user_id))
        db.execute(delete(Subscription).where(Subscription.user_id == user_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
