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

from src.core.caching import get_cache_critical, get_redis, set_cache_critical
from src.core.config import settings
from src.core.exceptions import AppException
from src.core.security import decode_access_token
from src.database.connection import session_factory
from src.users.models.credentials import UserCredentials
from src.users.models.session import UserSession
from src.users.repository.user import UserCredentialsRepository, UserSessionRepository
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.utils.exceptions import AccessDeniedError, InvalidAccessTokenError

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
    token: Annotated[str, Depends(oauth2_scheme)],
) -> CurrentUser:
    redis = get_redis(request)

    try:
        payload = decode_access_token(token)

        public_id = uuid.UUID(payload["sub"])
        session_id = int(payload["session_id"])
        atv = int(payload["atv"])
        role = UserRole(payload["role"])
        account_type = AccountType(payload["account_type"])

    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidAccessTokenError() from exc

    atv_key = _atv_cache_key(session_id)
    cached = await get_cache_critical(redis, atv_key)

    if cached is not None:
        try:
            cached_atv, cached_credentials_id = _unpack_atv_cache(cached)

        except ValueError:
            logger.warning("atv_cache_malformed", session_id=session_id, cached=cached)
            cached = None

    if cached is not None:
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

    user_session: (
        UserSession | None
    ) = await UserSessionRepository.get_user_session_by_id(session, session_id)

    if user_session is None:
        raise AppException(
            status_code=401,
            detail="Session not found or has been revoked.",
            error_code="INVALID_ACCESS_TOKEN",
        )

    credentials: (
        UserCredentials | None
    ) = await UserCredentialsRepository.get_user_credentials_by_id(
        session, user_session.credentials_id
    )

    if credentials is None or credentials.public_id != public_id:
        raise InvalidAccessTokenError()

    if user_session.access_token_version != atv:
        raise InvalidAccessTokenError()

    _verify_status(credentials)

    await set_cache_critical(
        redis,
        atv_key,
        _pack_atv_cache(user_session.access_token_version, credentials.id),
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


def require_roles(*roles: UserRole):
    def guard(current_user: current_user_dependency) -> CurrentUser:
        if current_user.role not in roles:
            raise AccessDeniedError()

        return current_user

    return guard


def _verify_status(credentials: UserCredentials) -> None:
    if credentials.status == UserStatus.ACTIVE:
        return

    if (
        credentials.status == UserStatus.PENDING_DELETION
        and credentials.deletion_scheduled_for is not None
        and credentials.deletion_scheduled_for > datetime.now(UTC)
    ):
        return

    status_errors: dict[UserStatus, tuple[str, str]] = {
        UserStatus.PENDING_ACTIVATION: (
            "Account has not been activated yet.",
            "ACCOUNT_PENDING_ACTIVATION",
        ),
        UserStatus.INACTIVE: (
            "Account is inactive.",
            "ACCOUNT_INACTIVE",
        ),
        UserStatus.PENDING_DELETION: (
            "Account deletion grace period has expired.",
            "ACCOUNT_PENDING_DELETION",
        ),
        UserStatus.GRADUATED: (
            "This account belongs to a graduated student.",
            "ACCOUNT_GRADUATED",
        ),
        UserStatus.EXPELLED: (
            "This account has been expelled.",
            "ACCOUNT_EXPELLED",
        ),
        UserStatus.WITHDRAWN: (
            "This account has been withdrawn.",
            "ACCOUNT_WITHDRAWN",
        ),
    }

    detail, error_code = status_errors.get(
        credentials.status,
        ("Account access denied.", "ACCOUNT_ACCESS_DENIED"),
    )

    raise AppException(status_code=401, detail=detail, error_code=error_code)


def _atv_cache_key(session_id: int) -> str:
    return f"session:{session_id}:atv"


def _pack_atv_cache(atv: int, credentials_id: int) -> str:
    return f"{atv}:{credentials_id}"


def _unpack_atv_cache(cached: str) -> tuple[int, int]:
    """
    Unpack the cached ATV string back into (atv, credentials_id).

    Raises ValueError if the cache value is malformed — treated as a cache
    miss by the caller, which will fall through to the DB path.
    """
    try:
        atv_str, credentials_id_str = cached.split(":", 1)

        return int(atv_str), int(credentials_id_str)

    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Malformed ATV cache value: {cached!r}") from exc
