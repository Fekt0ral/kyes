from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .database import engine
from .models import Base
from .routers import subscriptions
from .routers import users
from .logger import setup_logging, get_logger
from time import perf_counter

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    Base.metadata.create_all(bind=engine)
    logger.info("База данных успешно инициализирована")
    
    yield

app = FastAPI(
    title="Subscription Tracker API",
    description="Сервис для учета подписок",
    lifespan=lifespan
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Ошибка при обработке запроса", extra={
            "method": request.method,
            "path": request.url.path
        })
        raise
    duration_ms = (perf_counter() - start) * 1000
    logger.info(
        "HTTP %s %s -> %s (%.2fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms
    )
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc):
    errors = exc.errors()
    error = errors[0].get("msg") if errors else "Validation error"
    logger.warning("Ошибка валидации запроса: %s", error)
    
    return JSONResponse(
        status_code=422, #unprocessable entity
        content={"detail": error}
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception(f"Необработанная ошибка приложения: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

app.include_router(subscriptions.router)
app.include_router(users.router)