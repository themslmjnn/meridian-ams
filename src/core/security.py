import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.concurrency import run_in_threadpool
from passlib.context import CryptContext

import src.utils.exceptions as exceptions
from src.auth.schemas import CreateAccessToken, CreateRefreshToken
from src.core.config import get_settings

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_access_token(payload: CreateAccessToken) -> str:
    data = {
        "sub": str(payload.public_id),
        "role": payload.role,
        "account_type": payload.account_type,
        "session_id": payload.session_id,
        "atv": payload.access_token_version,
        "type": "access",
        "exp": datetime.now(UTC)
        + timedelta(minutes=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(UTC),
    }

    return jwt.encode(
        data, get_settings().JWT_SECRET_KEY, algorithm=get_settings().ALGORITHM
    )


def _decode_token(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=[get_settings().ALGORITHM])

        if payload.get("type") != "access":
            raise exceptions.InvalidTokenTypeError()

        return payload

    except jwt.ExpiredSignatureError as exc:
        raise exceptions.ExpiredAccessTokenError() from exc

    except jwt.InvalidTokenError as exc:
        raise exceptions.InvalidAccessTokenError() from exc


def decode_access_token(token: str) -> dict:
    try:
        return _decode_token(token, get_settings().JWT_SECRET_KEY)

    except ValueError:
        if not get_settings.JWT_SECRET_KEY_PREVIOUS:
            raise

        return _decode_token(token, get_settings().JWT_SECRET_KEY_PREVIOUS)


def create_refresh_token(payload: CreateRefreshToken) -> tuple[str, str]:
    data = {
        "sub": str(payload.public_id),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC)
        + timedelta(days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS),
    }

    raw_token = jwt.encode(
        data,
        get_settings().JWT_SECRET_KEY,
        algorithm=get_settings().ALGORITHM,
    )

    return raw_token, sha256(raw_token)


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            get_settings().JWT_SECRET_KEY,
            algorithms=[get_settings().ALGORITHM],
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


async def hash_password(password: str) -> str:
    return await run_in_threadpool(bcrypt_context.hash, password)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return await run_in_threadpool(
        bcrypt_context.verify, plain_password, hashed_password
    )


def generate_email_change_code() -> tuple[str, str]:
    raw_code = str(secrets.randbelow(900_000) + 100_000)

    return raw_code, sha256(raw_code)


def verify_email_change_code(raw_code: str, hashed_code: str) -> bool:
    return hmac.compare_digest(sha256(raw_code), hashed_code)
