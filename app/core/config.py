"""Environment-driven application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TicketFlow"
    app_environment: Literal["development", "test", "production"] = "development"

    database_url: str
    redis_url: str
    ticket_list_cache_ttl_seconds: int = Field(default=30, ge=1, le=3600)
    dashboard_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    webhook_delivery_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)

    jwt_secret: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)

    seeded_agent_email: EmailStr
    seeded_agent_password: SecretStr = Field(min_length=12)


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per process."""

    return Settings()  # type: ignore[call-arg]
