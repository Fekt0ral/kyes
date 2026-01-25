from fastapi import FastAPI
from contextlib import asynccontextmanager
from .database import engine
from .models import Base
from .routers import subscriptions
from .routers import users

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    print("База данных успешно инициализирована")
    
    yield

app = FastAPI(
    title="Subscription Tracker API",
    description="Сервис для учета подписок",
    lifespan=lifespan
)

app.include_router(subscriptions.router)
app.include_router(users.router)