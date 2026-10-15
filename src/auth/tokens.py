import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from src.core.config import get_settings
from src.users.utils.enums import AccountType, UserRole
from src.utils import exceptions

settings = get_settings()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_access_token(
    *,
    public_id: uuid.UUID,
    role: UserRole,
    account_type: AccountType,
    session_id: int,
    access_token_version: int,
) -> str:
    now = datetime.now(UTC)

    payload = {
        "sub": str(public_id),
        "role": role,
        "account_type": account_type,
        "session_id": session_id,
        "atv": access_token_version,
        "type": "access",
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRES_MINUTES),
        "iat": now,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )


def decode_access_token(access_token: str) -> dict:
    try:
        payload = jwt.decode(
            access_token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "sub", "session_id", "atv"]},
        )

        if payload.get("type") != "access":
            raise exceptions.InvalidTokenTypeError()

        return payload

    except jwt.ExpiredSignatureError as exc:
        raise exceptions.ExpiredAccessTokenError() from exc

    except jwt.InvalidTokenError as exc:
        raise exceptions.InvalidAccessTokenError() from exc


def create_refresh_token(public_id: uuid.UUID, session_id: int) -> tuple[str, str]:
    now = datetime.now(UTC)

    payload = {
        "sub": str(public_id),
        "session_id": session_id,
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRES_DAYS),
        "iat": now,
    }

    raw_refresh_token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )

    return raw_refresh_token, sha256(raw_refresh_token)


def decode_refresh_token(refresh_token: str) -> dict:
    try:
        payload = jwt.decode(
            refresh_token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "sub", "session_id", "jti"]},
        )

        if payload.get("type") != "refresh":
            raise exceptions.InvalidTokenTypeError()

        return payload

    except jwt.ExpiredSignatureError as exc:
        raise exceptions.ExpiredRefreshTokenError() from exc

    except jwt.InvalidTokenError as exc:
        raise exceptions.InvalidRefreshTokenError() from exc
