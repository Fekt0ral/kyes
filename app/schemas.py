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
    
    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str):
        name = v.strip()
        if not (2 <= len(name) <= 100):
            raise ValueError("Service name must be between 2 and 100 characters long.")
        return name
    
    @field_validator("next_payment") # на фронте потом можно сделать минимальную дату сегодня
    @classmethod
    def validate_next_payment(cls, v: date):
        if v < date.today():
            raise ValueError("Incorrect date: next payment must be today or in the future.")
        return v
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]):
        if v:
            category = v.strip()
            if not (2 <= len(category) <= 50):
                raise ValueError("Category must be between 2 and 50 characters long.")
            return category
        return v

class SubscriptionCreate(SubscriptionBase):
    pass

class SubscriptionRead(SubscriptionBase):
    id: int
    price_rub: float = 0.0
    model_config = {"from_attributes": True}
    
class SubscriptionUpdate(BaseModel):
    service_name: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    currency: Optional[Literal["RUB", "USD", "EUR"]] = None
    next_payment: Optional[date] = None
    category: Optional[str] = None
    
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
    @classmethod
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        email = v.strip()
        if not re.match(pattern, email):
            raise ValueError("Invalid email")
        return email

    @field_validator("password")
    @classmethod
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
    @classmethod
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