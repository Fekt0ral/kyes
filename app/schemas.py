from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class SubscriptionBase(BaseModel):
    service_name: str = Field(...)
    price: float = Field(..., gt=0)
    currency: str = Field(default="Rub")
    next_payment: date
    category: Optional[str] = None

class SubscriptionCreate(SubscriptionBase):
    pass # Все поля из базовой схемы нам нужны

class SubscriptionRead(SubscriptionBase):
    id: int
    model_config = {"from_attributes": True}
    
class UserCreate(BaseModel):
    email: str
    password: str
    name: str 

class UserRead(BaseModel):
    id: int
    email: str
    name: str
    
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str