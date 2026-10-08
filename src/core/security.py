import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi.concurrency import run_in_threadpool

import src.utils.exceptions as exceptions
from src.auth.schemas import CreateAccessToken, CreateRefreshToken
from src.core.config import get_settings

_BCRYPT_MAX_BYTES = 72

# Verified against when there is no real hash, so "user not found" and
# "wrong password" cost the same. Computed once at import (~250 ms).
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _keyed_hash(value: str) -> str:
    """HMAC-SHA256 with a server secret, for low-entropy values such as codes."""
    key = get_settings().JWT_SECRET_KEY.get_secret_value().encode()

    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def create_access_token(payload: CreateAccessToken) -> str:
    now = datetime.now(UTC)

    data = {
        "sub": str(payload.public_id),
        "role": payload.role,
        "account_type": payload.account_type,
        "session_id": payload.session_id,
        "atv": payload.access_token_version,
        "type": "access",
        "exp": now + timedelta(minutes=get_settings().ACCESS_TOKEN_EXPIRES_MINUTES),
        "iat": now,
    }

    return jwt.encode(
        data,
        get_settings().JWT_SECRET_KEY.get_secret_value(),
        algorithm=get_settings().ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            get_settings().JWT_SECRET_KEY.get_secret_value(),
            algorithms=[get_settings().ALGORITHM],
            options={"require": ["exp", "iat", "sub", "session_id", "atv"]},
        )

        if payload.get("type") != "access":
            raise exceptions.InvalidTokenTypeError()

        return payload

    except jwt.ExpiredSignatureError as exc:
        raise exceptions.ExpiredAccessTokenError() from exc

    except jwt.InvalidTokenError as exc:
        raise exceptions.InvalidAccessTokenError() from exc


def create_refresh_token(payload: CreateRefreshToken) -> tuple[str, str]:
    now = datetime.now(UTC)

    data = {
        "sub": str(payload.public_id),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "exp": now + timedelta(days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS),
        "iat": now,
    }

    raw_token = jwt.encode(
        data,
        get_settings().JWT_SECRET_KEY.get_secret_value(),
        algorithm=get_settings().ALGORITHM,
    )

    return raw_token, sha256(raw_token)


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            get_settings().JWT_SECRET_KEY.get_secret_value(),
            algorithms=[get_settings().ALGORITHM],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )

        if payload.get("type") != "refresh":
            raise exceptions.InvalidTokenTypeError()

        return payload

    except jwt.ExpiredSignatureError as exc:
        raise exceptions.ExpiredRefreshTokenError() from exc

    except jwt.InvalidTokenError as exc:
        raise exceptions.InvalidRefreshTokenError() from exc


def generate_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)

    return raw_token, sha256(raw_token)


def verify_token(raw_token: str, hashed_token: str) -> bool:
    return hmac.compare_digest(sha256(raw_token), hashed_token)


def _hash_password_sync(password: str) -> str:
    encoded = password.encode()
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {_BCRYPT_MAX_BYTES} bytes")

    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()


def _verify_password_sync(plain_password: str, hashed_password: str | None) -> bool:
    encoded = plain_password.encode()
    # Over-long input can never match; still do the work to keep timing flat.
    too_long = len(encoded) > _BCRYPT_MAX_BYTES
    target = hashed_password or _DUMMY_HASH

    try:
        matched = bcrypt.checkpw(encoded[:_BCRYPT_MAX_BYTES], target.encode())

    except ValueError:  # malformed stored hash
        return False

    return matched and not too_long and hashed_password is not None


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hash_password_sync, password)


async def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    return await run_in_threadpool(
        _verify_password_sync, plain_password, hashed_password
    )


def generate_email_change_code() -> tuple[str, str]:
    raw_code = str(secrets.randbelow(900_000) + 100_000)

    return raw_code, _keyed_hash(raw_code)


def verify_email_change_code(raw_code: str, hashed_code: str) -> bool:
    return hmac.compare_digest(_keyed_hash(raw_code), hashed_code)
