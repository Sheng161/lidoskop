from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://lidoskop:change-me@localhost:5432/lidoskop"
    redis_url: str = "redis://localhost:6379/0"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    lidoskop_master_key: str = ""
    crawler_user_agent: str = "Lidoskop/0.1 (+local-research; contact=owner)"
    crawler_max_pages: int = Field(default=12, ge=1, le=100)
    crawler_timeout_seconds: int = Field(default=15, ge=3, le=60)
    data_retention_days: int = Field(default=180, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
