from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import List, Literal, Optional
import re

# Subscription Schemas
class SubscriptionBase(BaseModel):
    service_name: str = Field(...)
    price: float = Field(..., gt=0)
    currency: Literal["RUB", "USD", "EUR"] = "RUB"
    next_payment: date
    category: Optional[str] = None

class SubscriptionCreate(SubscriptionBase):
    pass

class SubscriptionRead(SubscriptionBase):
    id: int
    price_rub: float = 0.0
    model_config = {"from_attributes": True}
    
class CategoryStat(BaseModel):
    category: str
    category_sum: float
    model_config = {"from_attributes": True}

class CategoryReport(BaseModel):
    category: str
    services: List[SubscriptionRead]
    total_monthly: float

class AllCategoriesReport(BaseModel):
    total_monthly: float
    categories: List[CategoryStat]
    model_config = {"from_attributes": True}
    
class SubscriptionDelete(BaseModel):
    id: int
    service_name: str
    model_config = {"from_attributes": True}
    
# User Schemas
class UserCreate(BaseModel):
    email: str
    password: str
    name: str 

    @field_validator("email")
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        email = v.strip()
        if not re.match(pattern, email):
            raise ValueError("Invalid email")
        return email

    @field_validator("password")
    def validate_password(cls, v):
        pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,30}$"
        password = v.strip()
        if not re.match(pattern, password):
            raise ValueError(
                "Password must be at least 8, at maximum 30 characters long, "
                "include uppercase and lowercase letters, "
                "a number, and a special character."
            )
        return password
    
    @field_validator("name")
    def validate_name(cls, v):
        pattern = r"^(?=.*[a-zA-Zа-яА-Я])[a-zA-Zа-яА-Я0-9\s-]{2,50}$"
        name = v.strip()
        if not re.match(pattern, name):
            raise ValueError(
                "Name must be between 2 and 50 characters long, "
                "contain letters or numbers "
                "and may not include special characters except hyphens."
            )
        return name

class UserRead(BaseModel):
    id: int
    email: str
    name: str
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str