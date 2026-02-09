from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    bot_token: SecretStr
    database_url: str = f"sqlite:///{BASE_DIR}/subscriptions.db"
    
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    
    cache_ttl: int = 600
    rate_limit_login_per_min: int = 10
    rate_limit_profile_per_day: int = 5
    telegram_support_chat_id: str | None = None
    telegram_bot_username: str | None = None
    telegram_link_token_ttl_minutes: int = 10
    
    log_level: str = "INFO"
    log_format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
    
    currency_api_url: str = "https://open.er-api.com/v6/latest/RUB"
    
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"

settings = Settings()
