import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

import src.utils.exceptions as exceptions
from src.core.caching import get_cache_critical, get_redis, set_cache_critical
from src.core.config import get_settings
from src.core.exceptions import AppException
from src.core.security import decode_access_token
from src.database.connection import session_factory
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserCredentialsRepository, UserSessionRepository
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.utils.cache_keys import SessionCacheKey

logger = structlog.get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session

        except Exception:
            await session.rollback()

            raise


session_dependency = Annotated[AsyncSession, Depends(get_session)]
redis_dependency = Annotated[Redis, Depends(get_redis)]


@dataclass
class CurrentUser:
    credentials_id: int
    public_id: uuid.UUID
    role: UserRole
    account_type: AccountType
    session_id: int


async def get_current_user(
    request: Request,
    session: session_dependency,
    redis: redis_dependency,
    access_token: Annotated[str, Depends(oauth2_scheme)],
) -> CurrentUser:
    try:
        payload = decode_access_token(access_token)

        public_id = uuid.UUID(payload["sub"])
        session_id = int(payload["session_id"])
        atv = int(payload["atv"])
        role = UserRole(payload["role"])
        account_type = AccountType(payload["account_type"])

    except (ValueError, KeyError, TypeError) as exc:
        raise exceptions.InvalidAccessTokenError() from exc

    atv_key = SessionCacheKey.access_token_version_key(session_id)
    unpacked_cached_atv = await get_cache_critical(redis, atv_key)

    if unpacked_cached_atv is not None:
        try:
            cached_atv, cached_credentials_id = SessionCacheKey.unpack_atv_cache(
                unpacked_cached_atv
            )

        except ValueError:
            logger.warning(
                "atv_cache_malformed", session_id=session_id, cached=unpacked_cached_atv
            )

            unpacked_cached_atv = None

    if unpacked_cached_atv is not None:
        if cached_atv != atv:
            raise exceptions.InvalidAccessTokenError()

        current_user = CurrentUser(
            credentials_id=cached_credentials_id,
            public_id=public_id,
            role=role,
            account_type=account_type,
            session_id=session_id,
        )

        request.state.user = current_user

        return current_user

    user_session = await UserSessionRepository.get_by_id(session, session_id)

    if user_session is None:
        raise exceptions.InvalidAccessTokenError(
            detail="Session not found or has been revoked"
        )

    credentials = await UserCredentialsRepository.get_by_id(
        session, user_session.credentials_id
    )

    if credentials is None or credentials.public_id != public_id:
        raise exceptions.InvalidAccessTokenError()

    if user_session.access_token_version != atv:
        raise exceptions.InvalidAccessTokenError()

    _verify_status(credentials)

    await set_cache_critical(
        redis,
        atv_key,
        SessionCacheKey.pack_atv_cache(
            user_session.access_token_version, credentials.id
        ),
        ex=get_settings().ACCESS_TOKEN_EXPIRES_MINUTES * 60,
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


def require_roles(*roles: UserRole):
    def guard(current_user: current_user_dependency) -> CurrentUser:
        if current_user.role not in roles:
            raise exceptions.AccessDeniedError()

        return current_user

    return guard


require_system_admin = Annotated[
    CurrentUser, Depends(require_roles(UserRole.SYSTEM_ADMIN))
]
require_director = Annotated[CurrentUser, Depends(require_roles(UserRole.DIRECTOR))]
require_guardian = Annotated[CurrentUser, Depends(require_roles(UserRole.GUARDIAN))]


STATUS_EXCEPTION_MAP: dict[UserStatus, type[AppException]] = {
    UserStatus.PENDING_ACTIVATION: exceptions.AccountNotActivatedError,
    UserStatus.INACTIVE: exceptions.AccountInactiveError,
    UserStatus.PENDING_DELETION: exceptions.ExpiredDeletionGracePeriodError,
    UserStatus.GRADUATED: exceptions.AccountGraduatedError,
    UserStatus.EXPELLED: exceptions.AccountExpelledError,
    UserStatus.WITHDRAWN: exceptions.AccountWithdrawnError,
}


def _verify_status(credentials: UserCredentials) -> None:
    if credentials.status == UserStatus.ACTIVE:
        return

    if (
        credentials.status == UserStatus.PENDING_DELETION
        and credentials.deletion_scheduled_for is not None
        and credentials.deletion_scheduled_for > datetime.now(UTC)
    ):
        return

    raise STATUS_EXCEPTION_MAP.get(
        credentials.status,
        exceptions.AccessDeniedError,
    )()
