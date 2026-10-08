import re

import pytest
from pydantic import ValidationError

from src.core.config import Settings

PROD_ENVS = ("staging", "production")


class TestAlgorithm:
    def test_default_is_hs256(self, make_settings: Settings):
        assert make_settings().ALGORITHM == "HS256"

    def test_non_hmac_algorithm_rejected(self, make_settings: Settings):
        with pytest.raises(ValidationError):
            make_settings(ALGORITHM="RS256")


class TestDerivedURLs:
    def test_database_url_computed_from_components(self, make_settings: Settings):
        s = make_settings(
            DB_USER="myuser",
            DB_PASSWORD="mypass",
            DB_HOST="db.example.com",
            DB_PORT=5433,
            DB_NAME="mydb",
        )

        assert s.DATABASE_URL == (
            "postgresql+asyncpg://myuser:mypass@db.example.com:5433/mydb"
        )

    def test_database_url_percent_encodes_credentials(self, make_settings: Settings):
        s = make_settings(DB_USER="user", DB_PASSWORD="p@ss/w:rd#1")

        assert s.DATABASE_URL == (
            "postgresql+asyncpg://user:p%40ss%2Fw%3Ard%231@localhost:5432/meridian_test"
        )

    def test_redis_url_without_password(self, make_settings: Settings):
        s = make_settings(
            REDIS_HOST="redis.example.com",
            REDIS_PORT=6380,
            REDIS_DB=2,
            REDIS_PASSWORD=None,
        )

        assert s.REDIS_URL == "redis://redis.example.com:6380/2"

    def test_redis_url_with_password(self, make_settings: Settings):
        s = make_settings(
            REDIS_HOST="redis.example.com",
            REDIS_PORT=6379,
            REDIS_DB=0,
            REDIS_PASSWORD="secret",
        )

        assert s.REDIS_URL == "redis://:secret@redis.example.com:6379/0"

    def test_redis_url_percent_encodes_password(self, make_settings: Settings):
        s = make_settings(REDIS_PASSWORD="p@ss")

        assert s.REDIS_URL == "redis://:p%40ss@localhost:6379/1"

    def test_passwords_not_exposed_in_repr(self, make_settings: Settings):
        s = make_settings(DB_PASSWORD="p@ss-unique", REDIS_PASSWORD="r@ss-unique")
        text = repr(s)

        for leaked in ("p@ss-unique", "p%40ss-unique", "r@ss-unique", "r%40ss-unique"):
            assert leaked not in text


class TestEnvironmentDerivedFlags:
    @pytest.mark.parametrize("env", ["development", "test"])
    def test_flags_off_outside_production_like(self, make_settings: Settings, env):
        s = make_settings(ENVIRONMENT=env)

        assert s.IS_PRODUCTION_LIKE is False
        assert s.COOKIE_SECURE is False
        assert s.METRICS_ENABLED is False

    @pytest.mark.parametrize("env", PROD_ENVS)
    def test_flags_on_in_production_like(self, make_settings: Settings, env):
        s = make_settings(ENVIRONMENT=env)

        assert s.IS_PRODUCTION_LIKE is True
        assert s.COOKIE_SECURE is True
        assert s.METRICS_ENABLED is True


class TestFieldValidatorsPort:
    @pytest.mark.parametrize("field", ["DB_PORT", "REDIS_PORT"])
    @pytest.mark.parametrize("port", [0, 65536, 99999])
    def test_invalid_port_raises(self, make_settings: Settings, field, port):
        with pytest.raises(
            ValidationError, match=f"Port must be between 1 and 65535, got {port}"
        ):
            make_settings(**{field: port})

    @pytest.mark.parametrize("port", [1, 65535])
    def test_port_boundaries_accepted(self, make_settings: Settings, port):
        assert port == make_settings(DB_PORT=port).DB_PORT


class TestFieldValidatorsHost:
    @pytest.mark.parametrize("field", ["DB_HOST", "REDIS_HOST"])
    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_host_raises(self, make_settings: Settings, field, value):
        with pytest.raises(ValidationError, match="Host cannot be empty or whitespace"):
            make_settings(**{field: value})

    def test_db_host_is_stripped(self, make_settings: Settings):
        assert make_settings(DB_HOST="  localhost  ").DB_HOST == "localhost"


class TestFieldValidatorsDBIdentifier:
    @pytest.mark.parametrize("field", ["DB_USER", "DB_NAME"])
    @pytest.mark.parametrize("value", ["", "  "])
    def test_empty_identifier_raises(self, make_settings: Settings, field, value):
        with pytest.raises(
            ValidationError,
            match="Database user and name cannot be empty or whitespace",
        ):
            make_settings(**{field: value})


class TestFieldValidatorsSecret:
    @pytest.mark.parametrize("field", ["JWT_SECRET_KEY", "CURSOR_SECRET_KEY"])
    def test_secret_too_short_raises(self, make_settings: Settings, field):
        with pytest.raises(
            ValidationError, match="Secret must be at least 32 characters"
        ):
            make_settings(**{field: "short"})

    def test_secret_exactly_32_chars_passes(self, make_settings: Settings):
        s = make_settings(JWT_SECRET_KEY="a" * 32)

        assert s.JWT_SECRET_KEY.get_secret_value() == "a" * 32


class TestFieldValidatorsTokenExpiry:
    def test_access_token_expiry_below_minimum_raises(self, make_settings: Settings):
        with pytest.raises(
            ValidationError, match="ACCESS_TOKEN_EXPIRES_MINUTES must be at least 15"
        ):
            make_settings(ACCESS_TOKEN_EXPIRES_MINUTES=14)

    def test_access_token_expiry_above_maximum_raises(self, make_settings: Settings):
        with pytest.raises(
            ValidationError, match="ACCESS_TOKEN_EXPIRES_MINUTES should not exceed 30"
        ):
            make_settings(ACCESS_TOKEN_EXPIRES_MINUTES=31)

    def test_refresh_token_expiry_below_minimum_raises(self, make_settings: Settings):
        with pytest.raises(
            ValidationError, match="REFRESH_TOKEN_EXPIRES_DAYS must be at least 7"
        ):
            make_settings(REFRESH_TOKEN_EXPIRES_DAYS=0)

    def test_refresh_token_expiry_above_maximum_raises(self, make_settings: Settings):
        with pytest.raises(
            ValidationError, match="REFRESH_TOKEN_EXPIRES_DAYS should not exceed 30"
        ):
            make_settings(REFRESH_TOKEN_EXPIRES_DAYS=31)


class TestFieldValidatorsLoginAttempt:
    def test_below_minimum_raises(self, make_settings: Settings):
        with pytest.raises(
            ValidationError, match="MAX_LOGIN_ATTEMPTS must be at least 3"
        ):
            make_settings(MAX_LOGIN_ATTEMPTS=2)

    def test_above_maximum_raises(self, make_settings: Settings):
        with pytest.raises(
            ValidationError, match="MAX_LOGIN_ATTEMPTS should not exceed 10"
        ):
            make_settings(MAX_LOGIN_ATTEMPTS=11)


class TestFieldValidatorsWorkEmailDomain:
    @pytest.mark.parametrize(
        "value", ["nodot", "", "  ", "school..edu", "a b.edu", "-school.edu"]
    )
    def test_invalid_domain_raises(self, make_settings: Settings, value):
        with pytest.raises(
            ValidationError,
            match=re.escape("WORK_EMAIL_DOMAIN must be a bare domain, e.g. 'school.edu'"),
        ):
            make_settings(WORK_EMAIL_DOMAIN=value)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("School.EDU", "school.edu"),
            ("@school.edu", "school.edu"),
            ("  mail.school.edu ", "mail.school.edu"),
        ],
    )
    def test_domain_normalised(self, make_settings: Settings, value, expected):
        assert expected == make_settings(WORK_EMAIL_DOMAIN=value).WORK_EMAIL_DOMAIN


class TestNumericBounds:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("DB_POOL_SIZE", 0),
            ("LOCKOUT_DURATION_MINUTES", 0),
            ("EMAIL_WORKER_INTERVAL", 0),
            ("EMAIL_WORKER_BATCH_SIZE", 0),
            ("REFRESH_GRACE_WINDOW_SECONDS", 121),
        ],
    )
    def test_out_of_range_raises(self, make_settings: Settings, field, value):
        with pytest.raises(ValidationError):
            make_settings(**{field: value})


class TestLogLevel:
    def test_default_is_info(self, make_settings: Settings):
        assert make_settings().LOG_LEVEL == "INFO"

    def test_invalid_level_raises(self, make_settings: Settings):
        with pytest.raises(ValidationError):
            make_settings(LOG_LEVEL="TRACE")


class TestCorsOrigins:
    @pytest.mark.parametrize("env", ["development", *PROD_ENVS])
    def test_wildcard_rejected(self, make_settings: Settings, env):
        with pytest.raises(
            ValidationError,
            match=re.escape(
                "CORS_ORIGINS must not contain '*' (credentials are enabled)"
            ),
        ):
            make_settings(ENVIRONMENT=env, CORS_ORIGINS=["*"])


class TestProductionRequirements:
    @pytest.mark.parametrize("env", PROD_ENVS)
    def test_valid_config_accepted(self, make_settings: Settings, env):
        assert env == make_settings(ENVIRONMENT=env).ENVIRONMENT

    @pytest.mark.parametrize("env", PROD_ENVS)
    def test_placeholder_secret_rejected(self, make_settings: Settings, env):
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY still contains"):
            make_settings(ENVIRONMENT=env, JWT_SECRET_KEY="your_" + "x" * 40)

    def test_identical_secrets_rejected(self, make_settings: Settings):
        with pytest.raises(ValidationError, match="must differ"):
            make_settings(
                ENVIRONMENT="production",
                JWT_SECRET_KEY="c" * 64,
                CURSOR_SECRET_KEY="c" * 64,
            )

    @pytest.mark.parametrize("name", ["APP_URL", "ALLOWED_HOSTS", "CORS_ORIGINS"])
    def test_unset_explicit_config_rejected(self, make_settings: Settings, name):
        with pytest.raises(ValidationError, match="must be set explicitly"):
            make_settings(ENVIRONMENT="production", _drop=(name,))

    def test_non_https_app_url_rejected(self, make_settings: Settings):
        with pytest.raises(ValidationError, match="APP_URL must use https"):
            make_settings(ENVIRONMENT="production", APP_URL="http://api.meridian.edu")

    def test_wildcard_allowed_hosts_rejected(self, make_settings: Settings):
        with pytest.raises(
            ValidationError, match=re.escape("ALLOWED_HOSTS must not contain '*'")
        ):
            make_settings(ENVIRONMENT="production", ALLOWED_HOSTS=["*"])

    @pytest.mark.parametrize("name", ["EMAIL_API_KEY", "MAIL_FROM"])
    def test_missing_email_config_rejected(self, make_settings: Settings, name):
        with pytest.raises(
            ValidationError, match="EMAIL_API_KEY and MAIL_FROM are required"
        ):
            make_settings(ENVIRONMENT="production", _drop=(name,))

    def test_all_problems_reported_together(self, make_settings: Settings):
        with pytest.raises(ValidationError) as exc:
            make_settings(ENVIRONMENT="production", _drop=("APP_URL", "EMAIL_API_KEY"))

        message = str(exc.value)

        assert "must be set explicitly" in message
        assert "EMAIL_API_KEY and MAIL_FROM are required" in message

    @pytest.mark.parametrize("env", ["development", "test"])
    def test_rules_not_enforced_outside_production_like(
        self, make_settings: Settings, env
    ):
        s = make_settings(
            ENVIRONMENT=env,
            JWT_SECRET_KEY="your_" + "x" * 40,
            _drop=("APP_URL", "EMAIL_API_KEY", "MAIL_FROM"),
        )

        assert env == s.ENVIRONMENT


class TestEnvironmentValidation:
    def test_invalid_environment_raises(self, make_settings: Settings):
        with pytest.raises(ValidationError):
            make_settings(ENVIRONMENT="local")

    @pytest.mark.parametrize("env", ["development", "test", *PROD_ENVS])
    def test_valid_environment_accepted(self, make_settings: Settings, env):
        assert env == make_settings(ENVIRONMENT=env).ENVIRONMENT


class TestRequiredFields:
    @pytest.mark.parametrize(
        "name",
        [
            "ENVIRONMENT",
            "DB_HOST",
            "DB_USER",
            "DB_PASSWORD",
            "DB_NAME",
            "REDIS_HOST",
            "REDIS_DB",
            "JWT_SECRET_KEY",
            "CURSOR_SECRET_KEY",
            "WORK_EMAIL_DOMAIN",
        ],
    )
    def test_missing_required_field_raises(self, make_settings: Settings, name):
        with pytest.raises(ValidationError):
            make_settings(_drop=(name,))
