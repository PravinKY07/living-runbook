from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    watsonx_apikey: str = Field(default="", repr=False)
    watsonx_project_id: str = ""
    watsonx_url: str = ""
    code_analysis_model: str = ""
    writer_model: str = ""

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    @property
    def session_configured(self) -> bool:
        """Return whether a non-empty session secret is configured."""
        return bool(self.session_secret.strip())


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()
