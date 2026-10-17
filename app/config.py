"""Application settings, loaded from environment variables."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

FailurePolicyName = Literal["rollback", "leave", "partial"]


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment variables.

    Field names map to upper-case env vars (e.g. ``BASE_URL``, ``FAILURE_POLICY``).
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    base_url: str = "https://hospital-directory.onrender.com"
    request_timeout: float = 30.0
    max_concurrency: int = 10
    max_retries: int = 2
    max_rows: int = 20
    failure_policy: FailurePolicyName = "rollback"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one read of the environment)."""
    return Settings()
