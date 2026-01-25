from pydantic import BaseModel, Field
from datetime import date
from typing import List, Literal, Optional

# Subscription Schemas
class SubscriptionBase(BaseModel):
    service_name: str = Field(...)
    price: float = Field(..., gt=0)
    currency: Literal["Rub", "USD", "EUR"] = "Rub"
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
    
class SubscriptionDelete(BaseModel):
    id: int
    service_name: str
    model_config = {"from_attributes": True}
    
# User Schemas
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