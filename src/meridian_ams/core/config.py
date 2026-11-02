import os
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, StringConstraints, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = os.getenv("ENVIRONMENT", "development")
_ENV_FILE = ".env.test" if _ENV == "test" else ".env"

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if os.path.exists(_ENV_FILE) else None,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_ignore_empty=True,
    )

    APP_NAME: str = "Meridian AMS"

    ENVIRONMENT: Literal["development", "test", "staging", "production"]

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    DB_HOST: NonEmptyStr
    DB_PORT: int = Field(ge=1, le=65535, default=5432)
    DB_USER: NonEmptyStr
    DB_PASSWORD: SecretStr
    DB_NAME: NonEmptyStr

    DB_POOL_TIMEOUT: int = Field(ge=1, le=120, default=5)
    DB_CONNECT_TIMEOUT: int = Field(ge=1, le=120, default=5)

    REDIS_HOST: NonEmptyStr
    REDIS_PORT: int = Field(ge=1, le=65535, default=6379)
    REDIS_PASSWORD: SecretStr | None = None
    REDIS_DB: int = Field(ge=0, le=15)

    ALGORITHM: Literal["HS256"] = "HS256"
    JWT_SECRET_KEY: SecretStr

    ACTIVATION_TOKEN_EXPIRES_HOURS: int = Field(ge=1, le=168, default=48)

    ACCESS_TOKEN_EXPIRES_MINUTES: int = Field(ge=15, le=30, default=15)
    REFRESH_TOKEN_EXPIRES_DAYS: int = Field(ge=7, le=30, default=7)

    WORK_EMAIL_DOMAIN: str

    RESEND_API_KEY: SecretStr
    MAIL_FROM: str = "noreply@meridian.edu"
    MAIL_FROM_NAME: str = "Meridian AMS"
    MAILTRAP_HOST: str = "sandbox.smtp.mailtrap.io"
    MAILTRAP_PORT: int = Field(ge=1, le=65535, default=587)
    MAILTRAP_USERNAME: str
    MAILTRAP_PASSWORD: SecretStr

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_required_secrets(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("Secret must be at least 32 characters")

        return v

    @field_validator("WORK_EMAIL_DOMAIN")
    @classmethod
    def validate_work_email_domain(cls, v: str) -> str:
        v = v.strip().lower().lstrip("@")

        if not v:
            raise ValueError("WORK_EMAIL_DOMAIN cannot be empty")

        return v

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{quote(self.DB_USER, safe='')}"
            f":{quote(self.DB_PASSWORD.get_secret_value(), safe='')}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{quote(self.DB_NAME, safe='')}"
        )

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            password = quote(self.REDIS_PASSWORD.get_secret_value(), safe="")

            return f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
