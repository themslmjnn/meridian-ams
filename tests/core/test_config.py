import pytest
from pydantic import ValidationError

from meridian_ams.core.config import Settings

REQUIRED_FIELDS = [
    "ENVIRONMENT",
    "DB_HOST",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "REDIS_HOST",
    "REDIS_DB",
    "JWT_SECRET_KEY",
    "WORK_EMAIL_DOMAIN",
]

OPTIONAL_FIELDS = [
    "APP_NAME",
    "LOG_LEVEL",
    "DB_PORT",
    "DB_POOL_TIMEOUT",
    "DB_CONNECT_TIMEOUT",
    "REDIS_PORT",
    "REDIS_PASSWORD",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRES_MINUTES",
    "REFRESH_TOKEN_EXPIRES_DAYS",
]

JWT_SECRET = "jwt-secret-value-" + "x" * 20


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A complete valid environment with every optional variable cleared."""

    for name in OPTIONAL_FIELDS:
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_USER", "school_user")
    monkeypatch.setenv("DB_PASSWORD", "db-secret-value")
    monkeypatch.setenv("DB_NAME", "meridian_test")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_DB", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
    monkeypatch.setenv("WORK_EMAIL_DOMAIN", "school.com")

    return monkeypatch


def build_settings() -> Settings:
    # _env_file=None: ignore .env / .env.test, only the environment counts
    return Settings(_env_file=None)


def failed_fields(exc_info: pytest.ExceptionInfo[ValidationError]) -> set[str]:
    return {str(error["loc"][0]) for error in exc_info.value.errors()}


class TestRequiredFields:
    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_missing_required_field_is_rejected(self, valid_env, field):
        valid_env.delenv(field)

        with pytest.raises(ValidationError) as exc_info:
            build_settings()

        assert failed_fields(exc_info) == {field}

    @pytest.mark.parametrize("value", ["", "   "], ids=["empty", "whitespace"])
    def test_blank_required_string_is_rejected(self, valid_env, value):
        valid_env.setenv("DB_HOST", value)

        with pytest.raises(ValidationError) as exc_info:
            build_settings()

        assert failed_fields(exc_info) == {"DB_HOST"}


class TestValidationRules:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("DB_PORT", "0"),
            ("DB_PORT", "65536"),
            ("REDIS_PORT", "0"),
            ("REDIS_PORT", "65536"),
            ("DB_POOL_TIMEOUT", "0"),
            ("DB_POOL_TIMEOUT", "121"),
            ("DB_CONNECT_TIMEOUT", "0"),
            ("DB_CONNECT_TIMEOUT", "121"),
            ("REDIS_DB", "-1"),
            ("REDIS_DB", "16"),
            ("ACTIVATION_TOKEN_EXPIRES_HOURS", "0"),
            ("ACTIVATION_TOKEN_EXPIRES_HOURS", "169"),
            ("ACCESS_TOKEN_EXPIRES_MINUTES", "14"),
            ("ACCESS_TOKEN_EXPIRES_MINUTES", "31"),
            ("REFRESH_TOKEN_EXPIRES_DAYS", "6"),
            ("REFRESH_TOKEN_EXPIRES_DAYS", "31"),
        ],
    )
    def test_out_of_range_number_is_rejected(self, valid_env, field, value):
        valid_env.setenv(field, value)

        with pytest.raises(ValidationError) as exc_info:
            build_settings()

        assert failed_fields(exc_info) == {field}

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("ENVIRONMENT", "banana"),
            ("LOG_LEVEL", "info"),
            ("ALGORITHM", "none"),
            ("ALGORITHM", "RS256"),
        ],
        ids=[
            "unknown_environment",
            "lowercase_log_level",
            "algorithm_none",
            "algorithm_other_than_hs256",
        ],
    )
    def test_invalid_choice_is_rejected(self, valid_env, field, value):
        valid_env.setenv(field, value)

        with pytest.raises(ValidationError) as exc_info:
            build_settings()

        assert failed_fields(exc_info) == {field}


class TestJWTSecret:
    def test_secret_shorter_than_32_characters_is_rejected(self, valid_env):
        valid_env.setenv("JWT_SECRET_KEY", "x" * 31)

        with pytest.raises(ValidationError) as exc_info:
            build_settings()

        assert failed_fields(exc_info) == {"JWT_SECRET_KEY"}

    def test_secret_of_exactly_32_characters_is_accepted(self, valid_env):
        valid_env.setenv("JWT_SECRET_KEY", "x" * 32)

        settings = build_settings()

        assert settings.JWT_SECRET_KEY.get_secret_value() == "x" * 32


class TestWorkEmailDomain:
    def test_domain_is_normalised(self, valid_env):
        valid_env.setenv("WORK_EMAIL_DOMAIN", "  @School.COM ")

        assert build_settings().WORK_EMAIL_DOMAIN == "school.com"

    @pytest.mark.parametrize("value", ["@", "   ", " @ "])
    def test_domain_that_is_empty_after_normalising_is_rejected(self, valid_env, value):
        valid_env.setenv("WORK_EMAIL_DOMAIN", value)

        with pytest.raises(ValidationError) as exc_info:
            build_settings()

        assert failed_fields(exc_info) == {"WORK_EMAIL_DOMAIN"}


class TestDefaults:
    def test_defaults_apply_when_only_required_fields_are_set(self, valid_env):
        settings = build_settings()

        assert settings.APP_NAME == "Meridian AMS"
        assert settings.LOG_LEVEL == "INFO"
        assert settings.DB_PORT == 5432
        assert settings.DB_POOL_TIMEOUT == 5
        assert settings.DB_CONNECT_TIMEOUT == 5
        assert settings.REDIS_PORT == 6379
        assert settings.REDIS_PASSWORD is None
        assert settings.ALGORITHM == "HS256"
        assert settings.ACTIVATION_TOKEN_EXPIRES_HOURS == 48
        assert settings.ACCESS_TOKEN_EXPIRES_MINUTES == 15
        assert settings.REFRESH_TOKEN_EXPIRES_DAYS == 7


class TestComputedURLs:
    def test_database_url_encodes_special_characters(self, valid_env):
        valid_env.setenv("DB_USER", "school user")
        valid_env.setenv("DB_PASSWORD", "p@ss:w/rd")

        settings = build_settings()

        assert settings.DATABASE_URL == (
            "postgresql+asyncpg://school%20user:p%40ss%3Aw%2Frd@localhost:5432/meridian_test"
        )

    def test_redis_url_with_password_encodes_it(self, valid_env):
        valid_env.setenv("REDIS_PASSWORD", "p@ss:w/rd")

        settings = build_settings()

        assert settings.REDIS_URL == "redis://:p%40ss%3Aw%2Frd@localhost:6379/1"

    def test_redis_url_without_password_has_no_credentials(self, valid_env):
        settings = build_settings()

        assert settings.REDIS_URL == "redis://localhost:6379/1"


class TestSecrets:
    def test_secrets_do_not_appear_in_repr(self, valid_env):
        valid_env.setenv("REDIS_PASSWORD", "redis-secret-value")

        text = repr(build_settings())

        assert "db-secret-value" not in text
        assert "redis-secret-value" not in text
        assert JWT_SECRET not in text
