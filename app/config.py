from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://booking:booking@localhost:25432/booking"
    )
    redis_url: str = "redis://localhost:26379/0"
    availability_cache_ttl_seconds: int = 10
    booking_ttl_minutes: int = 10
    debug: bool = False
    debug_host: str = "host.docker.internal"
    debug_port: int = 5678


@lru_cache
def get_settings() -> Settings:
    return Settings()
