import secrets
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import AuthRepository
from src.auth.schemas import CreateAccessToken, CreateRefreshToken, LoginResponse
from src.core.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from src.users.models.login_history import LoginHistory
from src.users.models.session import UserSession
from src.users.utils.enums import UserStatus
from src.utils.exceptions import (
    AccessDeniedError,
    AccountInactiveError,
    AccountLockedError,
    GracePeriodExpiredError,
    InvalidCredentialsError,
)

logger = structlog.get_logger(__name__)

_COOKIE_PATH = "/api/v1/auth/refresh"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


class AuthService:
    @staticmethod
    def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
        response.set_cookie(
            key="refresh_token",
            value=raw_refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="strict",
            max_age=_COOKIE_MAX_AGE,
            path=_COOKIE_PATH,
        )

    @staticmethod
    def _clear_refresh_cookie(response: Response) -> None:
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="strict",
            path=_COOKIE_PATH,
        )

    @staticmethod
    async def login(
        session: AsyncSession,
        response: Response,
        form_data: OAuth2PasswordRequestForm,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResponse:

        credentials = await AuthRepository.get_credentials_by_username(
            session, form_data.username
        )

        if credentials is None:
            await verify_password(
                form_data.password,
                "$2b$12$placeholder.hash.to.keep.timing.consistent.x",
            )

            logger.warning(
                "login_failed", reason="user_not_found", username=form_data.username
            )

            raise InvalidCredentialsError()

        lockout = credentials.login_lockout

        if lockout.locked_until and datetime.now(UTC) < lockout.locked_until:
            new_login_history = LoginHistory(
                session,
                credentials_id=credentials.id,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="account_locked",
            )

            session.add(new_login_history)
            await session.commit()

            logger.warning(
                "login_blocked",
                reason="account_locked",
                credentials_id=credentials.id,
                locked_until=lockout.locked_until.isoformat(),
            )

            raise AccountLockedError(
                detail=f"Account locked until {lockout.locked_until.strftime('%H:%M UTC')}"
            )

        if credentials.status == UserStatus.PENDING_ACTIVATION:
            new_login_history = LoginHistory(
                session,
                credentials_id=credentials.id,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="account_not_activated",
            )

            session.addd(new_login_history)
            await session.commit()

            raise AccountInactiveError()

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_DELETION,
        ):
            new_login_history = LoginHistory(
                session,
                credentials_id=credentials.id,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=f"account_{credentials.status.value}",
            )

            session.add(new_login_history)
            await session.commit()

            raise AccessDeniedError()

        if not await verify_password(
            form_data.password, credentials.password_hash or ""
        ):
            lockout.failed_attempts += 1
            lockout.last_failed_at = datetime.now(UTC)

            if lockout.failed_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                lockout.locked_until = datetime.now(UTC) + timedelta(
                    minutes=settings.LOCKOUT_DURATION_MINUTES
                )
                logger.warning(
                    "account_locked",
                    credentials_id=credentials.id,
                    failed_attempts=lockout.failed_attempts,
                    locked_until=lockout.locked_until.isoformat(),
                )

            new_login_history = LoginHistory(
                session,
                credentials_id=credentials.id,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="invalid_password",
            )

            session.add(new_login_history)
            await session.commit()

            logger.warning(
                "login_failed",
                reason="invalid_password",
                credentials_id=credentials.id,
                failed_attempts=lockout.failed_attempts,
            )

            raise InvalidCredentialsError()

        if credentials.status == UserStatus.PENDING_DELETION:
            if (
                credentials.deletion_scheduled_for is None
                or credentials.deletion_scheduled_for <= datetime.now(UTC)
            ):
                new_login_history = LoginHistory(
                    session,
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="deletion_grace_expired",
                )

                session.add(new_login_history)
                await session.commit()

                raise GracePeriodExpiredError()

            credentials.status = credentials.pre_deletion_status
            credentials.deletion_scheduled_for = None
            credentials.pre_deletion_status = None
            logger.info("deletion_implicitly_cancelled", credentials_id=credentials.id)

        lockout.failed_attempts = 0
        lockout.locked_until = None
        lockout.last_failed_at = None

        refresh_token_family = secrets.token_urlsafe(32)
        refresh_token_expires_at = datetime.now(UTC) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRES_DAYS
        )

        new_user_session = UserSession(
            session,
            credentials_id=credentials.id,
            refresh_token_hash="",
            refresh_token_family=refresh_token_family,
            refresh_token_expires_at=refresh_token_expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        session.add(new_user_session)
        await session.flush()

        raw_refresh_token, hashed_refresh_token = create_refresh_token(
            CreateRefreshToken(
                public_id=credentials.public_id,
                session_id=new_user_session.id,
            )
        )

        new_user_session.refresh_token_hash = hashed_refresh_token

        access_token = create_access_token(
            CreateAccessToken(
                public_id=credentials.public_id,
                role=credentials.role,
                account_type=credentials.account_type,
                session_id=new_user_session.id,
                access_token_version=new_user_session.access_token_version,
            )
        )

        new_login_history = LoginHistory(
            session,
            credentials_id=credentials.id,
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        session.add(new_login_history)
        await session.commit()

        logger.info(
            "login_success",
            credentials_id=credentials.id,
            role=credentials.role,
            session_id=new_user_session.id,
        )

        AuthService._set_refresh_cookie(response, raw_refresh_token)

        return LoginResponse(access_token=access_token, token_type="bearer")
