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

settings = Settings()