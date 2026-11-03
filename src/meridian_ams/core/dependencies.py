import uuid
from collections.abc import AsyncIterator, Callable, cast
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.auth.repositories.session import UserSessionRepository
from meridian_ams.auth.tokens import decode_access_token
from meridian_ams.core.config import get_settings
from meridian_ams.core.exceptions import AppException
from meridian_ams.users.models.credentials import UserCredentials
from meridian_ams.users.repositories.credentials import UserCredentialsRepository
from meridian_ams.users.utils.enums import AccountType, UserRole, UserStatus
from meridian_ams.utils.cache_keys import SessionCacheKey
from meridian_ams.utils.exceptions import (
    AccessDeniedError,
    AccountExpelledError,
    AccountGraduatedError,
    AccountInactiveError,
    AccountNotActivatedError,
    AccountWithdrawnError,
    InvalidAccessTokenError,
)

logger = structlog.get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.async_session_factory() as db_session:
        yield db_session


def get_redis(request: Request) -> Redis:
    return cast("Redis", request.app.state.redis)


db_session_dependency = Annotated[AsyncSession, Depends(get_db_session)]
redis_dependency = Annotated[Redis, Depends(get_redis)]


@dataclass
class CurrentUser:
    credentials_id: int
    public_id: uuid.UUID
    role: UserRole
    account_type: AccountType
    session_id: int


async def _read_atv_cache(
    redis: Redis, key: str, session_id: int
) -> tuple[int, int] | None:
    """Return (atv, credentials_id) from the cache, or None on a miss/malformed value."""

    packed_atv_cache = await redis.get(key)
    if packed_atv_cache is None:
        return None

    try:
        return SessionCacheKey.unpack_atv_cache(packed_atv_cache)

    except ValueError:
        logger.warning(
            "atv_cache_malformed",
            session_id=session_id,
            packed_atv_cache=packed_atv_cache,
        )

        return None


async def get_current_user(
    request: Request,
    db_session: db_session_dependency,
    redis: redis_dependency,
    access_token: Annotated[str | None, Depends(oauth2_scheme)],
) -> CurrentUser:
    if access_token is None:
        raise InvalidAccessTokenError(detail="Not authenticated")

    try:
        payload = decode_access_token(access_token)

        public_id = uuid.UUID(payload["sub"])
        session_id = int(payload["session_id"])
        atv = int(payload["atv"])
        role = UserRole(payload["role"])
        account_type = AccountType(payload["account_type"])

    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidAccessTokenError() from exc

    atv_key = SessionCacheKey.access_token_version_key(session_id)
    unpacked_atv_cache = await _read_atv_cache(redis, atv_key, session_id)

    if unpacked_atv_cache is not None:
        cached_atv, cached_credentials_id = unpacked_atv_cache

        if cached_atv != atv:
            raise InvalidAccessTokenError()

        current_user = CurrentUser(
            credentials_id=cached_credentials_id,
            public_id=public_id,
            role=role,
            account_type=account_type,
            session_id=session_id,
        )

        request.state.user = current_user

        return current_user

    user_session = await UserSessionRepository.get_by_id(db_session, session_id)

    if user_session is None:
        raise InvalidAccessTokenError(detail="Session not found or has been revoked")

    credentials = await UserCredentialsRepository.get_by_id(
        db_session, user_session.credentials_id
    )

    if credentials is None or credentials.public_id != public_id:
        raise InvalidAccessTokenError()

    if user_session.access_token_version != atv:
        raise InvalidAccessTokenError()

    verify_status(credentials)

    settings = get_settings()

    await redis.set(
        atv_key,
        SessionCacheKey.pack_atv_cache(
            user_session.access_token_version, credentials.id
        ),
        ex=settings.ACCESS_TOKEN_EXPIRES_MINUTES * 60,
    )

    current_user = CurrentUser(
        credentials_id=credentials.id,
        public_id=public_id,
        role=role,
        account_type=account_type,
        session_id=session_id,
    )

    request.state.user = current_user

    return current_user


current_user_dependency = Annotated[CurrentUser, Depends(get_current_user)]


STATUS_EXCEPTION_MAP: dict[UserStatus, type[AppException]] = {
    UserStatus.PENDING_ACTIVATION: AccountNotActivatedError,
    UserStatus.INACTIVE: AccountInactiveError,
    UserStatus.GRADUATED: AccountGraduatedError,
    UserStatus.EXPELLED: AccountExpelledError,
    UserStatus.WITHDRAWN: AccountWithdrawnError,
}


def verify_status(credentials: UserCredentials) -> None:
    if credentials.status == UserStatus.ACTIVE:
        return

    raise STATUS_EXCEPTION_MAP.get(
        credentials.status,
        AccessDeniedError,
    )()


def require_roles(*roles: UserRole) -> Callable[..., CurrentUser]:
    def guard(current_user: current_user_dependency) -> CurrentUser:
        if current_user.role not in roles:
            raise AccessDeniedError()

        return current_user

    return guard


require_system_admin = Annotated[
    CurrentUser, Depends(require_roles(UserRole.SYSTEM_ADMIN))
]
