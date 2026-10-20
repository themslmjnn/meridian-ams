import hashlib
import hmac
import secrets

import bcrypt
from fastapi.concurrency import run_in_threadpool

from src.core.config import get_settings

_BCRYPT_MAX_BYTES = 72

_DUMMY_HASH = bcrypt.hashpw(b"StrongPassword_123!", bcrypt.gensalt()).decode()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _keyed_hash(value: str) -> str:
    key = get_settings().JWT_SECRET_KEY.get_secret_value().encode()

    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


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
    too_long = len(encoded) > _BCRYPT_MAX_BYTES
    target = hashed_password or _DUMMY_HASH

    try:
        matched = bcrypt.checkpw(encoded[:_BCRYPT_MAX_BYTES], target.encode())

    except ValueError:
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
