"""
Application settings.
Loaded once from the environment / .env and cached for the process lifetime.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved from this file, not the working directory. A bare ".env" is looked
# up relative to CWD, so the app booted from backend/ but failed to find its
# settings from the repo root -- which made `pytest backend/tests/` blow up on
# a missing database_url while `cd backend && pytest tests/` passed.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    redis_url: str = "redis://localhost:6379/0"

    # Default limit for public endpoints
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    # Stricter limit for auth endpoints (login/register/refresh)
    strict_rate_limit_requests: int = 5
    strict_rate_limit_window_seconds: int = 60

    environment: str = "development"
    trusted_hosts: str = "*"

    # Kept as a plain string on purpose. pydantic-settings JSON-decodes any
    # complex field type (list/dict) straight from the env var, which made
    # the documented comma-separated form in .env.example crash on startup.
    # Parsing ourselves accepts BOTH forms. See cors_origins below.
    allowed_origins: str = "http://localhost:5173"

    @field_validator("jwt_secret_key")
    @classmethod
    def _secret_must_be_strong(cls, v: str) -> str:
        # A short secret makes HS256 signatures brute-forceable offline.
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters. "
                "Generate one with: openssl rand -hex 32"
            )
        return v

    @staticmethod
    def _split_list(raw: str) -> list[str]:
        raw = (raw or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            return [str(x).strip() for x in json.loads(raw)]
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def cors_origins(self) -> list[str]:
        """CORS allow-list. Accepts JSON (["a","b"]) or comma-separated (a,b)."""
        return self._split_list(self.allowed_origins)

    @property
    def trusted_host_list(self) -> list[str]:
        return self._split_list(self.trusted_hosts) or ["*"]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
