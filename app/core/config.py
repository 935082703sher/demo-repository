"""Environment-backed application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Demo settings containing no production credentials."""

    model_config = SettingsConfigDict(env_prefix="RTMC_", env_file=".env", extra="ignore")

    environment: str = "local"
    service_name: str = "rtmc-ai-assistant"
    version: str = "0.1.0"
    log_level: str = "INFO"
    privacy_notice_version: str = "demo-privacy-v1"


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-equivalent settings object per process."""
    return Settings()
