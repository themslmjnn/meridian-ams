import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.concurrency import run_in_threadpool
from passlib.context import CryptContext

from src.auth.schemas import CreateAccessToken, CreateRefreshToken
from src.core.config import get_settings
from src.utils.exceptions import (
    ExpiredAccessTokenError,
    ExpiredRefreshTokenError,
    InvalidAccessTokenError,
    InvalidRefreshTokenError,
    InvalidTokenTypeError,
)

settings = get_settings()

ALGORITHM = "HS256"

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(payload: CreateAccessToken) -> str:
    data = {
        "sub": str(payload.public_id),
        "role": payload.role,
        "account_type": payload.account_type,
        "session_id": payload.session_id,
        "atv": payload.access_token_version,
        "type": "access",
        "exp": datetime.now(UTC)
        + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRES_MINUTES),
        "iat": datetime.now(UTC),
    }

    return jwt.encode(data, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str, secret: str) -> dict:
    """
    Decode and verify a JWT against a specific secret.
    Raises ValueError on any failure — callers handle the exception.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])

        if payload.get("type") != "access":
            raise InvalidTokenTypeError()

        return payload

    except jwt.ExpiredSignatureError as exc:
        raise ExpiredAccessTokenError() from exc

    except jwt.InvalidTokenError as exc:
        raise InvalidAccessTokenError() from exc


def decode_access_token(token: str) -> dict:
    try:
        return _decode_token(token, settings.JWT_SECRET_KEY)

    except ValueError:
        if not settings.JWT_SECRET_KEY_PREVIOUS:
            raise

        return _decode_token(token, settings.JWT_SECRET_KEY_PREVIOUS)


def create_refresh_token(payload: CreateRefreshToken) -> tuple[str, str]:
    raw_refresh_token = jwt.encode(
        {
            "sub": str(payload.public_id),
            "type": "refresh",
            "jti": secrets.token_urlsafe(16),
            "exp": datetime.now(UTC)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRES_DAYS),
        },
        settings.JWT_SECRET_KEY,
        algorithm=ALGORITHM,
    )

    hashed_refresh_token = hashlib.sha256(raw_refresh_token.encode()).hexdigest()

    return raw_refresh_token, hashed_refresh_token


def decode_refresh_token(refresh_token: str) -> dict:
    try:
        payload = jwt.decode(
            refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        if payload.get("type") != "refresh":
            raise InvalidTokenTypeError()

        return payload

    except jwt.ExpiredSignatureError as exc:
        raise ExpiredRefreshTokenError() from exc

    except jwt.InvalidTokenError as exc:
        raise InvalidRefreshTokenError() from exc


def generate_activation_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)

    return raw, _sha256(raw)


def verify_activation_token(raw_token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(_sha256(raw_token), stored_hash)


async def hash_password(password: str) -> str:
    return await run_in_threadpool(bcrypt_context.hash, password)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return await run_in_threadpool(
        bcrypt_context.verify, plain_password, hashed_password
    )


# Internal helpers
def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
