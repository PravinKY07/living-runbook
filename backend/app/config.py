from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
LOCAL_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings for the backend.

    Values are read from environment variables. Secrets have no usable default
    and must be supplied by the runtime environment when required.
    """

    app_name: str = "living-runbook"
    version: str = "0.1.0"
    debug: bool = False
    database_path: str = "./data/living_runbook.db"
    session_secret: str = Field(default="", repr=False)
    session_https_only: bool = True
    cors_origins: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_file=LOCAL_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_path")
    @classmethod
    def resolve_database_path(cls, value: str) -> str:
        """Resolve relative local paths from the backend, not the shell cwd."""
        path = Path(value)
        if path.is_absolute():
            return str(path)
        return str((BACKEND_ROOT / path).resolve())

    @property
    def session_configured(self) -> bool:
        """Return whether a non-empty session secret is configured."""
        return bool(self.session_secret.strip())


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()
