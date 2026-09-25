from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings for Phase 0.

    Values are read from environment variables. All fields have safe
    defaults so the application starts without any configuration.
    """

    app_name: str = "living-runbook"
    version: str = "0.1.0"
    debug: bool = False

    model_config = SettingsConfigDict(
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance.

    Using lru_cache means the environment is read once at first call and
    reused for every subsequent call — no repeated disk or env lookups.
    """
    return Settings()
