from sqlalchemy import Column, Integer, String, ForeignKey, Float, Date
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    subscriptions = relationship("Subscription", back_populates="owner")

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True)
    service_name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="RUB")
    next_payment = Column(Date, nullable=False)
    category = Column(String, nullable=True)
    link = Column(String, nullable=True)
    
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="subscriptions")