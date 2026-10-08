import os
import re
from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = os.getenv("ENVIRONMENT", "development")
_ENV_FILE_MAP = {
    "test": ".env.test",
}
_ENV_FILE = _ENV_FILE_MAP.get(_ENV, ".env")

_DOMAIN_RE = re.compile(
    r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if os.path.exists(_ENV_FILE) else None,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_ignore_empty=True,
    )

    ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"

    ENVIRONMENT: Literal["development", "test", "staging", "production"]
    IS_PRODUCTION_LIKE: bool = False
    APP_NAME: str = "Meridian AMS"
    APP_URL: str = "http://localhost:8000"
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    DB_HOST: str
    DB_PORT: int = 5432
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_NAME: str

    DB_POOL_SIZE: int = Field(10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(20, ge=0, le=200)
    DB_POOL_TIMEOUT: int = Field(5, ge=1, le=120)
    DB_POOL_RECYCLE: int = Field(3600, ge=60)

    DB_CONNECT_TIMEOUT: int = Field(10, ge=1, le=60)
    DB_STATEMENT_TIMEOUT_MS: int = Field(30_000, ge=1_000)
    DB_IDLE_IN_TX_TIMEOUT_MS: int = Field(60_000, ge=1_000)

    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: SecretStr | None = None
    REDIS_DB: int = Field(ge=0)

    JWT_SECRET_KEY: SecretStr

    ACCESS_TOKEN_EXPIRES_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRES_DAYS: int = 7
    REFRESH_GRACE_WINDOW_SECONDS: int = Field(60, ge=0, le=120)

    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = Field(30, ge=1)

    CURSOR_SECRET_KEY: SecretStr

    ACTIVATION_TOKEN_EXPIRES_HOURS: int = Field(48, ge=1, le=168)
    EMAIL_CHANGE_CODE_EXPIRES_MINUTES: int = Field(15, ge=1, le=60)
    RESET_PASSWORD_EXPIRES_MINUTES: int = Field(60, ge=1, le=120)

    IDEMPOTENCY_KEY_TTL: int = Field(60 * 60 * 24, ge=1)
    IDEMPOTENCY_PROCESSING_TTL: int = Field(60 * 5, ge=1)

    WORK_EMAIL_DOMAIN: str

    GRADING_PERIOD_TYPE: Literal["semester", "quarter", "trimester"] = "semester"

    EMAIL_WORKER_INTERVAL: int = Field(60, ge=1)
    EMAIL_WORKER_BATCH_SIZE: int = Field(10, ge=1, le=100)
    DELETION_WORKER_INTERVAL: int = Field(3600, ge=60)

    EMAIL_API_KEY: str | None = None
    MAIL_FROM: str | None = None
    MAIL_FROM_NAME: str | None = "Meridian AMS"

    MAILTRAP_HOST: str | None = "sandbox.smtp.mailtrap.io"
    MAILTRAP_PORT: int | None = 587
    MAILTRAP_USERNAME: str | None = None
    MAILTRAP_PASSWORD: SecretStr | None = None

    SENTRY_DSN: str | None = None

    # Derived fields — computed by model_validator, never set directly in .env
    COOKIE_SECURE: bool = False
    METRICS_ENABLED: bool = False

    @property
    def DATABASE_URL(self) -> str:
        """Async SQLAlchemy URL. Computed on access; credentials are percent-encoded."""

        return (
            f"postgresql+asyncpg://{quote(self.DB_USER, safe='')}"
            f":{quote(self.DB_PASSWORD.get_secret_value(), safe='')}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{quote(self.DB_NAME, safe='')}"
        )

    @property
    def REDIS_URL(self) -> str:
        """Redis URL. Computed on access; password is percent-encoded."""

        if self.REDIS_PASSWORD:
            password = quote(self.REDIS_PASSWORD.get_secret_value(), safe="")

            return f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: list[str]) -> list[str]:
        if "*" in v:
            raise ValueError(
                "CORS_ORIGINS must not contain '*' (credentials are enabled)"
            )

        return v

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

    @field_validator("JWT_SECRET_KEY", "CURSOR_SECRET_KEY")
    @classmethod
    def validate_required_secrets(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("Secret must be at least 32 characters")

        return v

    @field_validator("ACCESS_TOKEN_EXPIRES_MINUTES")
    @classmethod
    def validate_access_token_expiry(cls, v: int) -> int:
        if v < 15:
            raise ValueError("ACCESS_TOKEN_EXPIRES_MINUTES must be at least 15")
        if v > 30:
            raise ValueError("ACCESS_TOKEN_EXPIRES_MINUTES should not exceed 30")

        return v

    @field_validator("REFRESH_TOKEN_EXPIRES_DAYS")
    @classmethod
    def validate_refresh_token_expiry(cls, v: int) -> int:
        if v < 7:
            raise ValueError("REFRESH_TOKEN_EXPIRES_DAYS must be at least 7")
        if v > 30:
            raise ValueError("REFRESH_TOKEN_EXPIRES_DAYS should not exceed 30")

        return v

    @field_validator("MAX_LOGIN_ATTEMPTS")
    @classmethod
    def validate_max_login_attempts(cls, v: int) -> int:
        if v < 3:
            raise ValueError("MAX_LOGIN_ATTEMPTS must be at least 3")
        if v > 10:
            raise ValueError("MAX_LOGIN_ATTEMPTS should not exceed 10")

        return v

    @field_validator("WORK_EMAIL_DOMAIN")
    @classmethod
    def validate_work_email_domain(cls, v: str) -> str:
        v = v.strip().lower().lstrip("@")

        if not _DOMAIN_RE.fullmatch(v):
            raise ValueError(
                "WORK_EMAIL_DOMAIN must be a bare domain, e.g. 'school.edu'"
            )

        return v

    @model_validator(mode="after")
    def validate_production_requirements(self) -> "Settings":
        """Reject placeholder, reused, or missing config in staging/production."""

        if self.ENVIRONMENT not in ("staging", "production"):
            return self

        errors: list[str] = []

        sensitive = {
            "JWT_SECRET_KEY": self.JWT_SECRET_KEY.get_secret_value(),
            "CURSOR_SECRET_KEY": self.CURSOR_SECRET_KEY.get_secret_value(),
            "DB_PASSWORD": self.DB_PASSWORD.get_secret_value(),
        }
        if self.EMAIL_API_KEY:
            sensitive["EMAIL_API_KEY"] = self.EMAIL_API_KEY

        if sensitive["JWT_SECRET_KEY"] == sensitive["CURSOR_SECRET_KEY"]:
            errors.append("JWT_SECRET_KEY and CURSOR_SECRET_KEY must differ")

        missing = [
            name
            for name in ("ALLOWED_HOSTS", "CORS_ORIGINS", "APP_URL")
            if name not in self.model_fields_set
        ]
        if missing:
            errors.append(f"{', '.join(missing)} must be set explicitly")

        if not self.APP_URL.startswith("https://"):
            errors.append("APP_URL must use https")

        if "*" in self.ALLOWED_HOSTS:
            errors.append("ALLOWED_HOSTS must not contain '*'")

        if not self.EMAIL_API_KEY or not self.MAIL_FROM:
            errors.append("EMAIL_API_KEY and MAIL_FROM are required")

        if self.DB_IDLE_IN_TX_TIMEOUT_MS <= self.DB_STATEMENT_TIMEOUT_MS:
            errors.append(
                "DB_IDLE_IN_TX_TIMEOUT_MS must be greater than DB_STATEMENT_TIMEOUT_MS"
            )

        if errors:
            raise ValueError(
                f"Invalid {self.ENVIRONMENT} configuration: " + "; ".join(errors)
            )

        return self

    @model_validator(mode="after")
    def derive_computed_fields(self) -> "Settings":
        """
        Derive environment-dependent flags.

        COOKIE_SECURE and METRICS_ENABLED are derived from ENVIRONMENT so
        they cannot be accidentally misconfigured — staging always behaves
        like production for all security concerns.
        """

        self.IS_PRODUCTION_LIKE = self.ENVIRONMENT in ("staging", "production")

        self.COOKIE_SECURE = self.IS_PRODUCTION_LIKE
        self.METRICS_ENABLED = self.IS_PRODUCTION_LIKE

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
