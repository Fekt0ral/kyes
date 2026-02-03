from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone
from typing import Annotated
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from ..database import get_db
from .. import schemas, crud, security, models
from ..logger import get_logger

router = APIRouter(prefix="/auth", tags=["users"])
logger = get_logger(__name__)

DBSession = Annotated[Session, Depends(get_db)]
CurUser = Annotated[models.User, Depends(security.get_current_user)]

@router.post("/register", response_model=schemas.UserRead)
def register(
    user: schemas.UserCreate, 
    db: DBSession
):
    email_check = crud.get_user_by_email(db, email=user.email)
    if email_check:
        logger.info("Попытка регистрации с уже существующим email", extra={"email": user.email})
        raise HTTPException(status_code=400, detail="Email already registered")
    
    created = crud.create_user(db=db, user=user)
    logger.info("Пользователь зарегистрирован", extra={"user_id": created.id, "email": created.email})
    return created

@router.post("/login", response_model=schemas.Token)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    db: DBSession
):
    user = crud.get_user_by_email(db, form_data.username) # named username in OAuth
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        logger.warning("Неуспешная попытка входа", extra={"email": form_data.username})
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = security.create_access_token(data={"sub": str(user.id)})
    logger.info("Пользователь вошел в систему", extra={"user_id": user.id, "email": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=schemas.UserRead)
def read_me(current_user: CurUser):
    logger.info("Запрошен профиль пользователя", extra={"user_id": current_user.id})
    return current_user

@router.patch("/me/preferences", response_model=schemas.UserRead)
def update_preferences(
    update_data: schemas.UserPreferencesUpdate,
    db: DBSession,
    current_user: CurUser
):
    db_user = crud.update_user_preferred_currency(
        db=db,
        user_id=current_user.id,
        preferred_currency=update_data.preferred_currency
    )
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info(
        "Обновлены настройки пользователя",
        extra={"user_id": current_user.id, "preferred_currency": update_data.preferred_currency}
    )
    return db_user

@router.patch("/me", response_model=schemas.UserRead)
def update_me(
    update_data: schemas.UserUpdate,
    db: DBSession,
    current_user: CurUser
):
    def _to_naive_utc(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cooldown = timedelta(days=1)
    email_to_set = None
    name_to_set = None
    hashed_password = None
    last_email_change = None
    last_name_change = None
    last_password_change = None
    password_changed_at = None

    if update_data.password:
        if not update_data.current_password:
            raise HTTPException(status_code=400, detail="Current password is required to change password")
        if not security.verify_password(update_data.current_password, current_user.hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect current password")
        last_password_change = _to_naive_utc(current_user.last_password_change)
        if last_password_change and (now - last_password_change) < cooldown:
            raise HTTPException(status_code=429, detail="Password can be changed once per day")

    if update_data.email and update_data.email != current_user.email:
        existing = crud.get_user_by_email(db, update_data.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        last_email_change = _to_naive_utc(current_user.last_email_change)
        if last_email_change and (now - last_email_change) < cooldown:
            raise HTTPException(status_code=429, detail="Email can be changed once per day")

    if update_data.name and update_data.name != current_user.name:
        last_name_change = _to_naive_utc(current_user.last_name_change)
        if last_name_change and (now - last_name_change) < cooldown:
            raise HTTPException(status_code=429, detail="Name can be changed once per day")

    if update_data.email and update_data.email != current_user.email:
        email_to_set = update_data.email
        last_email_change = now

    if update_data.name and update_data.name != current_user.name:
        name_to_set = update_data.name
        last_name_change = now

    if update_data.password:
        hashed_password = security.get_password_hash(update_data.password)
        last_password_change = now
        password_changed_at = now

    if not any([email_to_set, name_to_set, hashed_password]):
        raise HTTPException(status_code=400, detail="No changes to update")

    db_user = crud.update_user_fields(
        db=db,
        user_id=current_user.id,
        email=email_to_set,
        name=name_to_set,
        hashed_password=hashed_password,
        password_changed_at=password_changed_at,
        last_email_change=last_email_change,
        last_name_change=last_name_change,
        last_password_change=last_password_change
    )
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    logger.info(
        "Пользователь обновил профиль",
        extra={
            "user_id": current_user.id,
            "email_changed": bool(email_to_set),
            "name_changed": bool(name_to_set),
            "password_changed": bool(hashed_password)
        }
    )
    return db_user
