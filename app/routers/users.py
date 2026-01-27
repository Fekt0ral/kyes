from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from ..database import get_db
from .. import schemas, crud, security

router = APIRouter(tags=["users"])

DBSession = Annotated[Session, Depends(get_db)]

@router.post("/register", response_model=schemas.UserRead)
def register_user(
    user: schemas.UserCreate, 
    db: DBSession
):
    email_check = crud.get_user_by_email(db, email=user.email)
    if email_check:
        raise HTTPException(status_code=400, detail="Email already registered")

    username_check = crud.get_user_by_nickname(db, name=user.name)
    if username_check:
        raise HTTPException(status_code=400, detail="Nickname already taken")
    
    return crud.create_user(db=db, user=user)

@router.post("/login", response_model=schemas.Token)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    db: DBSession
):
    user = crud.get_user_by_nickname(db, form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = security.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}