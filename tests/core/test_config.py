import pytest
from pydantic import ValidationError

from src.core.config import ALGORITHM, Settings


def make_valid_settings(**overrides) -> Settings:
    """
    Return a valid Settings instance with all required fields populated.
    Pass keyword overrides to test specific field behaviour.
    """
    defaults = {
        "ENVIRONMENT": "test",
        "DB_HOST": "localhost",
        "DB_PORT": 5432,
        "DB_USER": "meridian",
        "DB_PSSW": "meridian",
        "DB_NAME": "meridian_test",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": 6379,
        "REDIS_DB": 0,
        "JWT_SECRET_KEY": "a" * 64,
        "CURSOR_SECRET_KEY": "b" * 32,
        "WORK_EMAIL_DOMAIN": "school.edu",
    }

    defaults.update(overrides)

    return Settings.model_validate(defaults)


# ALGORITHM constant
def test_algorithm_constant_is_hs256():
    assert ALGORITHM == "HS256"


# Derived URLs
def test_database_url_computed_from_components():
    s = make_valid_settings(
        DB_USER="myuser",
        DB_PSSW="mypass",
        DB_HOST="db.example.com",
        DB_PORT=5433,
        DB_NAME="mydb",
    )

    assert s.DATABASE_URL == (
        "postgresql+asyncpg://myuser:mypass@db.example.com:5433/mydb"
    )


def test_redis_url_computed_without_password():
    s = make_valid_settings(
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6380,
        REDIS_DB=2,
        REDIS_PASSWORD=None,
    )

    assert s.REDIS_URL == "redis://redis.example.com:6380/2"


def test_redis_url_computed_with_password():
    s = make_valid_settings(
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6379,
        REDIS_DB=0,
        REDIS_PASSWORD="secret",
    )

    assert s.REDIS_URL == "redis://:secret@redis.example.com:6379/0"


# Environment-derived flags
def test_cookie_secure_false_in_development():
    s = make_valid_settings(ENVIRONMENT="development")

    assert s.COOKIE_SECURE is False


def test_cookie_secure_false_in_test():
    s = make_valid_settings(ENVIRONMENT="test")

    assert s.COOKIE_SECURE is False


def test_cookie_secure_true_in_staging():
    s = make_valid_settings(ENVIRONMENT="staging")

    assert s.COOKIE_SECURE is True


def test_cookie_secure_true_in_production():
    s = make_valid_settings(ENVIRONMENT="production")

    assert s.COOKIE_SECURE is True


def test_metrics_enabled_false_in_development():
    s = make_valid_settings(ENVIRONMENT="development")

    assert s.METRICS_ENABLED is False


def test_metrics_enabled_true_in_staging():
    s = make_valid_settings(ENVIRONMENT="staging")

    assert s.METRICS_ENABLED is True


def test_metrics_enabled_true_in_production():
    s = make_valid_settings(ENVIRONMENT="production")

    assert s.METRICS_ENABLED is True


# Field validators — port
def test_invalid_db_port_zero_raises():
    with pytest.raises(ValidationError, match="Port must be between"):
        make_valid_settings(DB_PORT=0)


def test_invalid_db_port_too_high_raises():
    with pytest.raises(ValidationError, match="Port must be between"):
        make_valid_settings(DB_PORT=65536)


def test_valid_db_port_boundary_low():
    s = make_valid_settings(DB_PORT=1)

    assert s.DB_PORT == 1


def test_valid_db_port_boundary_high():
    s = make_valid_settings(DB_PORT=65535)

    assert s.DB_PORT == 65535


def test_invalid_redis_port_raises():
    with pytest.raises(ValidationError, match="Port must be between"):
        make_valid_settings(REDIS_PORT=99999)


# Field validators — host
def test_empty_db_host_raises():
    with pytest.raises(ValidationError, match="Host cannot be empty"):
        make_valid_settings(DB_HOST="   ")


def test_empty_redis_host_raises():
    with pytest.raises(ValidationError, match="Host cannot be empty"):
        make_valid_settings(REDIS_HOST="")


def test_db_host_is_stripped():
    s = make_valid_settings(DB_HOST="  localhost  ")

    assert s.DB_HOST == "localhost"


# Field validators — DB identifier
def test_empty_db_user_raises():
    with pytest.raises(ValidationError, match="cannot be empty"):
        make_valid_settings(DB_USER="  ")


def test_empty_db_name_raises():
    with pytest.raises(ValidationError, match="cannot be empty"):
        make_valid_settings(DB_NAME="")


# Field validators — secret
def test_jwt_secret_too_short_raises():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        make_valid_settings(JWT_SECRET_KEY="short")


def test_cursor_secret_too_short_raises():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        make_valid_settings(CURSOR_SECRET_KEY="tooshort")


def test_jwt_secret_exactly_32_chars_passes():
    s = make_valid_settings(JWT_SECRET_KEY="a" * 32)

    assert len(s.JWT_SECRET_KEY) == 32


# Field validators — token expiry
def test_access_token_expiry_below_minimum_raises():
    with pytest.raises(ValidationError, match="at least 1"):
        make_valid_settings(ACCESS_TOKEN_EXPIRE_MINUTES=0)


def test_access_token_expiry_above_maximum_raises():
    with pytest.raises(ValidationError, match="should not exceed 60"):
        make_valid_settings(ACCESS_TOKEN_EXPIRE_MINUTES=61)


def test_refresh_token_expiry_below_minimum_raises():
    with pytest.raises(ValidationError, match="at least 1"):
        make_valid_settings(REFRESH_TOKEN_EXPIRE_DAYS=0)


def test_refresh_token_expiry_above_maximum_raises():
    with pytest.raises(ValidationError, match="should not exceed 90"):
        make_valid_settings(REFRESH_TOKEN_EXPIRE_DAYS=91)


# Field validators — login attempt
def test_max_login_attempts_below_minimum_raises():
    with pytest.raises(ValidationError, match="at least 3"):
        make_valid_settings(MAX_LOGIN_ATTEMPTS=2)


def test_max_login_attempts_above_maximum_raises():
    with pytest.raises(ValidationError, match="should not exceed 20"):
        make_valid_settings(MAX_LOGIN_ATTEMPTS=21)


# Field validators — work email domain
def test_work_email_domain_without_dot_raises():
    with pytest.raises(ValidationError, match="valid domain"):
        make_valid_settings(WORK_EMAIL_DOMAIN="nodot")


def test_work_email_domain_empty_raises():
    with pytest.raises(ValidationError, match="valid domain"):
        make_valid_settings(WORK_EMAIL_DOMAIN="  ")


def test_work_email_domain_normalised_to_lowercase():
    s = make_valid_settings(WORK_EMAIL_DOMAIN="School.EDU")

    assert s.WORK_EMAIL_DOMAIN == "school.edu"


# ENVIRONMENT validation
def test_invalid_environment_raises():
    with pytest.raises(ValidationError):
        make_valid_settings(ENVIRONMENT="local")


def test_valid_environments_all_accepted():
    for env in ("development", "test", "staging", "production"):
        s = make_valid_settings(ENVIRONMENT=env)

        assert env == s.ENVIRONMENT
