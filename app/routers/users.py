from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from ..database import get_db
from .. import schemas, crud, security

router = APIRouter(tags=["users"])

@router.post("/register", response_model=schemas.UserRead)
def register_user(
    user: schemas.UserCreate, 
    db: Session = Depends(get_db)
):
    email_check = crud.get_user_by_email(db, email=user.email)
    if email_check:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    name_check = crud.get_user_by_name(db, name=user.name)
    if name_check:
        raise HTTPException(status_code=400, detail="Name already taken")
    
    return crud.create_user(db=db, user=user)

@router.post("/token", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_name(db, form_data.username)
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token = security.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}