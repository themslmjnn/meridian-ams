import pytest
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine

from meridian_ams.core.config import Settings
from meridian_ams.database.connection import build_engine


@pytest.fixture
def development_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Valid settings with ENVIRONMENT=development, read only from the environment."""

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_USER", "school_user")
    monkeypatch.setenv("DB_PASSWORD", "db-secret-value")
    monkeypatch.setenv("DB_NAME", "meridian_test")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_DB", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret-value-" + "x" * 20)
    monkeypatch.setenv("WORK_EMAIL_DOMAIN", "school.com")
    monkeypatch.setenv("RESEND_API_KEY", "resend-key")
    monkeypatch.setenv("MAILTRAP_USERNAME", "mailtrap-user")
    monkeypatch.setenv("MAILTRAP_PASSWORD", "mailtrap-password")

    return Settings(_env_file=None)


def test_build_engine_uses_a_real_pool_outside_tests(
    development_settings: Settings,
) -> None:
    engine = build_engine(development_settings)

    assert isinstance(engine, AsyncEngine)
    assert not isinstance(engine.pool, NullPool)
