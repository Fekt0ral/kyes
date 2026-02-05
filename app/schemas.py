from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import List, Literal, Optional
import re

# Shared types
Currency = Literal["RUB", "USD", "EUR"]

# Subscription Schemas
class SubscriptionBase(BaseModel):
    model_config = {"extra": "forbid"}
    
    service_name: str = Field(...)
    price: float = Field(..., gt=0)
    currency: Currency = "RUB"
    next_payment: date
    category: Optional[str] = None
    link: Optional[str] = None
    
    @classmethod
    def _validate_service_name(cls, v: str):
        name = v.strip()
        if not (2 <= len(name) <= 100):
            raise ValueError("Service name must be between 2 and 100 characters long.")
        return name
    
    @classmethod
    def _validate_date(cls, v: date):
        if v < date.today():
            raise ValueError("Incorrect date: next payment must be today or in the future.")
        return v
    
    @classmethod
    def _validate_category(cls, v: str):
        category = v.strip()
        if not (2 <= len(category) <= 50):
            raise ValueError("Category must be between 2 and 50 characters long.")
        return category
    
    @classmethod
    def _validate_link(cls, v: Optional[str]):
        if v is not None:
            link = v.strip()
            if not link:
                return None
            pattern = r'^https?://[^\s/$.?#].[^\s]*$'
            if not re.match(pattern, link):
                raise ValueError("Invalid URL format")
            return link
        return None
    
    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str):
        return cls._validate_service_name(v)
    
    @field_validator("next_payment") # на фронте потом можно сделать минимальную дату сегодня
    @classmethod
    def validate_next_payment(cls, v: date):
        return cls._validate_date(v)
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]):
        return cls._validate_category(v) if v else v
    
    @field_validator("link")
    @classmethod
    def validate_link(cls, v: Optional[str]):
        return cls._validate_link(v) if v else v

class SubscriptionCreate(SubscriptionBase):
    pass

class SubscriptionRead(SubscriptionBase):
    id: int
    display_price: float = 0.0
    display_currency: Currency = "RUB"
    model_config = {"from_attributes": True}
    
class SubscriptionUpdate(BaseModel):
    service_name: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    currency: Optional[Currency] = None
    next_payment: Optional[date] = None
    category: Optional[str] = None
    link: Optional[str] = None
    
    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: Optional[str]):
        return SubscriptionBase._validate_service_name(v) if v else v
    
    @field_validator("next_payment")
    @classmethod
    def validate_next_payment(cls, v: Optional[date]):
        return SubscriptionBase._validate_date(v) if v else v
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]):
        return SubscriptionBase._validate_category(v) if v else v
    
    @field_validator("link")
    @classmethod
    def validate_link(cls, v: Optional[str]):
        return SubscriptionBase._validate_link(v) if v else v
    
class CategoryStat(BaseModel):
    category: str
    category_sum: float
    model_config = {"from_attributes": True}

class CategoryReport(BaseModel):
    category: str
    currency: Currency = "RUB"
    total_monthly: float
    services: List[SubscriptionRead]

class AllCategoriesReport(BaseModel):
    currency: Currency = "RUB"
    total_monthly: float
    categories: List[CategoryStat]
    model_config = {"from_attributes": True}
    
class SubscriptionDelete(BaseModel):
    id: int
    service_name: str
    model_config = {"from_attributes": True}
    
class DuplicateWarning(BaseModel):
    warning: str
    existing_subscriptions: List[SubscriptionRead]
    message: str = "Subscription with this name already exists. Use force=true to create anyway."
    
# User Schemas
class UserCreate(BaseModel):
    email: str
    password: str
    name: str 
    preferred_currency: Currency = "RUB"

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
    preferred_currency: Currency = "RUB"
    model_config = {"from_attributes": True}

class UserPreferencesUpdate(BaseModel):
    preferred_currency: Currency

class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]):
        return UserCreate.validate_email(v) if v else v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]):
        return UserCreate.validate_password(v) if v else v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]):
        return UserCreate.validate_name(v) if v else v

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str | None = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str