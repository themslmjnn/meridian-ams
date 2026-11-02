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
]

OPTIONAL_FIELDS = [
    "APP_NAME",
    "LOG_LEVEL",
    "DB_PORT",
    "DB_POOL_TIMEOUT",
    "DB_CONNECT_TIMEOUT",
    "REDIS_PORT",
    "REDIS_PASSWORD",
]


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
        ],
        ids=["unknown_environment", "lowercase_log_level"],
    )
    def test_invalid_choice_is_rejected(self, valid_env, field, value):
        valid_env.setenv(field, value)

        with pytest.raises(ValidationError) as exc_info:
            build_settings()

        assert failed_fields(exc_info) == {field}


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
    def test_passwords_do_not_appear_in_repr(self, valid_env):
        valid_env.setenv("REDIS_PASSWORD", "redis-secret-value")

        text = repr(build_settings())

        assert "db-secret-value" not in text
        assert "redis-secret-value" not in text
