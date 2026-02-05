from sqlalchemy import Column, Integer, String, ForeignKey, Float, Date, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    preferred_currency = Column(String, nullable=False, default="RUB")
    password_changed_at = Column(DateTime, nullable=False, default=datetime.now(timezone.utc))
    last_email_change = Column(DateTime, nullable=True)
    last_name_change = Column(DateTime, nullable=True)
    last_password_change = Column(DateTime, nullable=True)

    subscriptions = relationship("Subscription", back_populates="owner")
    refresh_tokens = relationship("RefreshToken", back_populates="owner", cascade="all, delete-orphan")

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

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="refresh_tokens")
