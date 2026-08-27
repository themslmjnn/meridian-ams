import os
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALGORITHM = "HS256"


_ENV = os.getenv("ENVIRONMENT", "development")
_ENV_FILE_MAP = {
    "test": ".env.test",
}
_ENV_FILE = _ENV_FILE_MAP.get(_ENV, ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if os.path.exists(_ENV_FILE) else None,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "test", "staging", "production"]
    APP_NAME: str = "Meridian AMS"
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    DB_HOST: str
    DB_PORT: int = 5432
    DB_USER: str
    DB_PSSW: str
    DB_NAME: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600

    # Computed in derive_computed_fields — do not set in .env
    DATABASE_URL: str = ""

    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0

    # Computed in derive_computed_fields — do not set in .env
    REDIS_URL: str = ""

    JWT_SECRET: str
    JWT_SECRET_PREVIOUS: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_GRACE_WINDOW_SECONDS: int = 60
    CURSOR_SECRET: str

    WORK_EMAIL_DOMAIN: str
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 30

    GRADING_PERIOD_TYPE: Literal["semester", "quarter", "trimester"] = "semester"

    EMAIL_WORKER_INTERVAL: int = 60
    DELETION_WORKER_INTERVAL: int = 3600

    EMAIL_API_KEY: str | None = None
    MAIL_FROM: str | None = None
    MAIL_FROM_NAME: str = "Meridian AMS"

    SENTRY_DSN: str | None = None

    # Derived fields — computed by model_validator, never set directly in .env
    COOKIE_SECURE: bool = False
    METRICS_ENABLED: bool = False

    @field_validator("DB_PORT", "REDIS_PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")

        return v

    @field_validator("DB_HOST", "REDIS_HOST")
    @classmethod
    def validate_host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Host cannot be empty or whitespace")

        return v.strip()

    @field_validator("DB_USER", "DB_NAME")
    @classmethod
    def validate_db_identifiers(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Database user and name cannot be empty or whitespace")

        return v.strip()

    @field_validator("JWT_SECRET", "CURSOR_SECRET")
    @classmethod
    def validate_secrets_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "Secret must be at least 32 characters. "
                "Generate with: openssl rand -hex 32"
            )

        return v

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_access_token_expiry(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be at least 1")
        if v > 60:
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES should not exceed 60 — "
                "use refresh tokens for long-lived sessions"
            )

        return v

    @field_validator("REFRESH_TOKEN_EXPIRE_DAYS")
    @classmethod
    def validate_refresh_token_expiry(cls, v: int) -> int:
        if v < 1:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be at least 1")
        if v > 90:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS should not exceed 90")

        return v

    @field_validator("MAX_LOGIN_ATTEMPTS")
    @classmethod
    def validate_max_login_attempts(cls, v: int) -> int:
        if v < 3:
            raise ValueError("MAX_LOGIN_ATTEMPTS must be at least 3")
        if v > 20:
            raise ValueError("MAX_LOGIN_ATTEMPTS should not exceed 20")

        return v

    @field_validator("WORK_EMAIL_DOMAIN")
    @classmethod
    def validate_work_email_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or "." not in v:
            raise ValueError(
                "WORK_EMAIL_DOMAIN must be a valid domain, e.g. 'school.edu'"
            )

        return v

    @model_validator(mode="after")
    def derive_computed_fields(self) -> "Settings":
        """
        Compute all derived fields from their raw components.

        DATABASE_URL and REDIS_URL are built here so the rest of the app
        reads .DATABASE_URL / .REDIS_URL without knowing how they were
        constructed — Railway injects individual vars, not full DSNs.

        COOKIE_SECURE and METRICS_ENABLED are derived from ENVIRONMENT so
        they cannot be accidentally misconfigured — staging always behaves
        like production for all security concerns.
        """
        self.DATABASE_URL = (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PSSW}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

        if self.REDIS_PASSWORD:
            self.REDIS_URL = (
                f"redis://:{self.REDIS_PASSWORD}"
                f"@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        else:
            self.REDIS_URL = (
                f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )

        is_production_like = self.ENVIRONMENT in ("staging", "production")
        self.COOKIE_SECURE = is_production_like
        self.METRICS_ENABLED = is_production_like

        return self


@lru_cache
def get_settings() -> Settings:
    """
    Return the cached Settings instance.

    Using @lru_cache ensures a single Settings object is created per process.
    Tests can bypass the cache by calling Settings() directly with overrides,
    or by clearing the cache with get_settings.cache_clear().
    """
    return Settings()
