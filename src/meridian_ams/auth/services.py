from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from redis import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.auth import cookies
from meridian_ams.auth.helpers import describe_user_agent
from meridian_ams.auth.models.login_history import LoginHistory
from meridian_ams.auth.models.session import UserSession
from meridian_ams.auth.repositories.login_lockout import UserLoginLockoutRepository
from meridian_ams.auth.repositories.session import UserSessionRepository
from meridian_ams.auth.schemas import LoginResponse
from meridian_ams.auth.tokens import create_access_token, create_refresh_token
from meridian_ams.core.email.service import send_email_in_background
from meridian_ams.core.email.templates.auth import send_new_login_notification_email
from meridian_ams.core.redis.wrappers import delete_cache_critical
from meridian_ams.core.security import generate_token, verify_password
from meridian_ams.emails.enums import EmailType
from meridian_ams.users.repositories.credentials import UserCredentialsRepository
from meridian_ams.users.utils.enums import UserStatus
from meridian_ams.users.utils.schemas import LoadOptionsSchema
from meridian_ams.utils.cache_keys import SessionCacheKey
from meridian_ams.utils.exceptions import (
    AccessDeniedError,
    AccountLockedError,
    AccountNotActivatedError,
    InvalidCredentialsError,
)

logger = structlog.get_logger(__name__)


class AuthService:
    @staticmethod
    async def login(
        request: Request,
        response: Response,
        db_session: AsyncSession,
        redis: Redis,
        form_data: OAuth2PasswordRequestForm,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResponse:
        settings = request.app.state.settings

        credentials = await UserCredentialsRepository.get_by_username(
            db_session,
            form_data.username,
            load_options=LoadOptionsSchema(
                load_identity=True,
                load_login_lockout=True,
            ),
        )
        if credentials is None:
            await verify_password(form_data.password, hashed_password=None)

            logger.warning(
                "login_failed",
                username=form_data.username,
                failure_reason="user_not_found",
            )

            raise InvalidCredentialsError()

        lockout = credentials.login_lockout

        if lockout.locked_until and datetime.now(UTC) < lockout.locked_until:
            db_session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="account_locked",
                )
            )

            await db_session.commit()

            logger.warning(
                "login_failed",
                credentials_id=credentials.id,
                locked_until=lockout.locked_until.isoformat(),
                failure_reason="account_locked",
            )

            raise AccountLockedError(
                detail=f"Account locked until {lockout.locked_until.strftime('%H:%M UTC')}"
            )

        if not await verify_password(
            form_data.password, credentials.password_hash or ""
        ):
            fresh_lockout = await UserLoginLockoutRepository.get_by_credentials_id(
                db_session, credentials.id
            )

            fresh_lockout.failed_attempts += 1
            fresh_lockout.last_failed_at = datetime.now(UTC)

            if fresh_lockout.failed_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                fresh_lockout.locked_until = datetime.now(UTC) + timedelta(
                    minutes=settings.LOCKOUT_DURATION_MINUTES
                )

                logger.warning(
                    "account_locked",
                    credentials_id=credentials.id,
                    failed_attempts=fresh_lockout.failed_attempts,
                    locked_until=fresh_lockout.locked_until.isoformat(),
                )

            db_session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="invalid_password",
                )
            )

            await db_session.commit()

            logger.warning(
                "login_failed",
                credentials_id=credentials.id,
                failed_attempts=fresh_lockout.failed_attempts,
                failure_reason="invalid_password",
            )

            raise InvalidCredentialsError()

        if credentials.status == UserStatus.PENDING_ACTIVATION:
            db_session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="account_not_activated",
                )
            )

            await db_session.commit()

            logger.warning(
                "login_failed",
                credentials_id=credentials.id,
                failure_reason="account_not_activated",
            )

            raise AccountNotActivatedError()

        if credentials.status != (UserStatus.ACTIVE):
            db_session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason=f"account_{credentials.status.value}",
                )
            )

            await db_session.commit()

            logger.warning(
                "login_failed",
                credentials_id=credentials.id,
                failure_reason=f"account_{credentials.status.value}",
            )

            raise AccessDeniedError()

        lockout.failed_attempts = 0
        lockout.locked_until = None
        lockout.last_failed_at = None

        incoming_device_id = request.cookies.get("device_id")
        existing_session = None
        evicted_session_id = None

        if incoming_device_id:
            existing_session = await UserSessionRepository.get_by_device_id(
                db_session,
                credentials_id=credentials.id,
                device_id=incoming_device_id,
            )

        if existing_session is not None:
            device_id = incoming_device_id

            raw_refresh_token, hashed_refresh_token = create_refresh_token(
                public_id=credentials.public_id,
                session_id=existing_session.id,
            )

            existing_session.refresh_token_hash = hashed_refresh_token
            existing_session.refresh_token_expires_at = datetime.now(UTC) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRES_DAYS
            )
            existing_session.ip_address = ip_address
            existing_session.user_agent = user_agent
            existing_session.last_active_at = datetime.now(UTC)

            await db_session.flush()

            user_session = existing_session

        else:
            session_count = await UserSessionRepository.get_session_count(
                db_session, credentials.id
            )
            if session_count >= settings.MAX_SESSIONS_PER_USER:
                evicted_session_id = await UserSessionRepository.evict_oldest_session(
                    db_session, credentials.id
                )

                logger.info(
                    "session_evicted",
                    credentials_id=credentials.id,
                    reason="session_cap_reached",
                    max_cap=settings.MAX_SESSIONS_PER_USER,
                )

            device_id, _ = generate_token()

            user_session = UserSession(
                credentials_id=credentials.id,
                refresh_token_hash="",
                refresh_token_expires_at=datetime.now(UTC)
                + timedelta(days=settings.REFRESH_TOKEN_EXPIRES_DAYS),
                user_agent=user_agent,
                ip_address=ip_address,
                device_id=device_id,
            )

            db_session.add(user_session)
            await db_session.flush()

            raw_refresh_token, hashed_refresh_token = create_refresh_token(
                public_id=credentials.public_id,
                session_id=user_session.id,
            )

            user_session.refresh_token_hash = hashed_refresh_token

        access_token = create_access_token(
            public_id=credentials.public_id,
            role=credentials.role,
            account_type=credentials.account_type,
            session_id=user_session.id,
            access_token_version=user_session.access_token_version,
        )

        db_session.add(
            LoginHistory(
                credentials_id=credentials.id,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

        await db_session.commit()

        if evicted_session_id is not None:
            await delete_cache_critical(
                redis, SessionCacheKey.access_token_version_key(evicted_session_id)
            )

        if not existing_session:
            login_time = datetime.now(UTC).strftime("%B %d, %Y at %H:%M UTC")

            send_email_in_background(
                send_new_login_notification_email(
                    to_email=credentials.email,
                    user_agent=describe_user_agent(user_agent),
                    login_time=login_time,
                ),
                email_type=EmailType.NEW_LOGIN,
            )

        logger.info(
            "user_logged_in",
            credentials_id=credentials.id,
            role=credentials.role,
            session_id=user_session.id,
            device="existing" if existing_session else "new",
        )

        cookies.set_refresh_token_cookie(response, raw_refresh_token)
        cookies.set_device_id_cookie(response, device_id)

        return LoginResponse(access_token=access_token, token_type="bearer")
