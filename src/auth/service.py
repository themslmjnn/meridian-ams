import secrets
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

import src.utils.exceptions as exceptions
from src.auth import cookies
from src.auth.helpers import describe_user_agent
from src.auth.repository import AuthRepository
from src.auth.schemas import (
    ActivateAccount,
    LoginResponse,
    PasswordResetRequestPublic,
    ResetPassword,
)
from src.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from src.core.caching import delete_cache_critical
from src.core.config import get_settings
from src.core.dependencies import CurrentUser, verify_status
from src.core.email.service import send_email_in_background
from src.core.security import (
    generate_token,
    hash_password,
    sha256,
    verify_password,
    verify_token,
)
from src.emails.models import Email
from src.emails.templates.authentication import (
    build_reset_password_email,
    send_account_activated_email,
    send_guardian_account_reactivated_email,
    send_new_login_notification_email,
)
from src.emails.templates.security import send_password_changed_confirmation
from src.emails.utils.enums import EmailType
from src.users.models.login_history import LoginHistory
from src.users.models.password_reset import UserPasswordReset
from src.users.models.session import UserSession
from src.users.repository.credentials import UserCredentialsRepository
from src.users.repository.session import UserSessionRepository
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import UserNotPendingActivationError
from src.users.utils.schemas import LoadOptionsSchema
from src.utils.cache_keys import SessionCacheKey

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
        settings = get_settings()

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

            raise exceptions.InvalidCredentialsError()

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

            raise exceptions.AccountLockedError(
                detail=f"Account locked until {lockout.locked_until.strftime('%H:%M UTC')}"
            )

        if not await verify_password(
            form_data.password, credentials.password_hash or ""
        ):
            fresh_lockout = await AuthRepository.get_login_lockout_by_credentials_id(
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

            raise exceptions.InvalidCredentialsError()

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

            raise exceptions.AccountNotActivatedError()

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_DELETION,
        ):
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

            raise exceptions.AccessDeniedError()

        should_send_account_reactivation_email = False

        if credentials.status == UserStatus.PENDING_DELETION:
            if (
                credentials.deletion_scheduled_for is None
                or credentials.deletion_scheduled_for <= datetime.now(UTC)
            ):
                db_session.add(
                    LoginHistory(
                        credentials_id=credentials.id,
                        success=False,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        failure_reason="deletion_grace_expired",
                    )
                )

                await db_session.commit()

                raise exceptions.InvalidCredentialsError()

            credentials.pre_transition_status = credentials.status
            credentials.status = UserStatus.ACTIVE
            credentials.deletion_scheduled_for = None

            should_send_account_reactivation_email = True

            logger.info(
                "deletion_implicitly_cancelled",
                credentials_id=credentials.id,
                detail="user_logged_in_within_grace_period",
            )

        lockout.failed_attempts = 0
        lockout.locked_until = None
        lockout.last_failed_at = None

        incoming_device_id = request.cookies.get("device_id")
        existing_session = None
        evicted_session_id = None

        if incoming_device_id:
            existing_session = await AuthRepository.get_session_by_device_id(
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
            session_count = await AuthRepository.get_session_count(
                db_session, credentials.id
            )
            if session_count >= settings.MAX_SESSIONS_PER_USER:
                evicted_session_id = await AuthRepository.evict_oldest_session(
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
                refresh_token_hash="",  # set below after flush gives us session.id
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

        if evicted_session_id is not None:
            await delete_cache_critical(
                redis, SessionCacheKey.access_token_version_key(evicted_session_id)
            )

        await db_session.commit()

        if should_send_account_reactivation_email:
            send_email_in_background(
                send_guardian_account_reactivated_email(to_email=credentials.email),
                email_type=EmailType.GUARDIAN_ACCOUNT_REACTIVATED,
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

    @staticmethod
    async def logout(
        response: Response,
        db_session: AsyncSession,
        redis: Redis,
        current_user: CurrentUser,
    ) -> None:
        user_session = await UserSessionRepository.get_by_id(
            db_session, current_user.session_id
        )
        if user_session is not None:
            await db_session.delete(user_session)
            await db_session.commit()

        await delete_cache_critical(
            redis, SessionCacheKey.access_token_version_key(current_user.session_id)
        )

        cookies.clear_refresh_token_cookie(response)

        logger.info(
            "user_logged_out",
            credentials_id=current_user.credentials_id,
            session_id=current_user.session_id,
        )

    @staticmethod
    async def refresh_token(
        response: Response,
        db_session: AsyncSession,
        redis: Redis,
        raw_refresh_token: str,
    ) -> LoginResponse:
        settings = get_settings()

        try:
            payload = decode_refresh_token(raw_refresh_token)
            session_id = int(payload["session_id"])

        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "refresh_token_rotation_failed",
                failure_reason="invalid_jwt",
                error=str(exc),
            )

            raise exceptions.InvalidRefreshTokenError() from exc

        # Row lock: concurrent refreshes for one session are serialised.
        user_session = await UserSessionRepository.get_by_id(
            db_session, session_id, for_update=True
        )
        if (
            user_session is None
            or user_session.refresh_token_hash is None
            or user_session.refresh_token_expires_at is None
        ):
            logger.warning(
                "refresh_token_rotation_failed",
                session_id=session_id,
                failure_reason="session_not_found_or_incomplete",
            )

            raise exceptions.InvalidRefreshTokenError()

        if datetime.now(UTC) > user_session.refresh_token_expires_at:
            logger.warning(
                "refresh_token_rotation_failed",
                failure_reason="refresh_token_expired",
                session_id=session_id,
            )

            raise exceptions.ExpiredRefreshTokenError()

        matches_current = verify_token(
            raw_refresh_token, user_session.refresh_token_hash
        )

        if not matches_current:
            await UserSessionRepository.invalidate_session(user_session)

            await db_session.commit()

            await delete_cache_critical(
                redis, SessionCacheKey.access_token_version_key(session_id)
            )

            logger.warning(
                "refresh_security_violation",
                session_id=session_id,
                action="session_invalidated",
            )

            raise exceptions.InvalidRefreshTokenError()

        credentials = await UserCredentialsRepository.get_by_id(
            db_session, user_session.credentials_id
        )
        if credentials is None:
            raise exceptions.InvalidRefreshTokenError()

        verify_status(credentials)

        new_raw_refresh_token, new_hashed_refresh_token = create_refresh_token(
            public_id=credentials.public_id, session_id=user_session.id
        )

        user_session.refresh_token_hash = new_hashed_refresh_token
        user_session.refresh_token_expires_at = datetime.now(UTC) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRES_DAYS
        )
        user_session.last_active_at = datetime.now(UTC)

        access_token = create_access_token(
            public_id=credentials.public_id,
            role=credentials.role,
            account_type=credentials.account_type,
            session_id=user_session.id,
            access_token_version=user_session.access_token_version,
        )

        await db_session.commit()

        logger.info(
            "refresh_token_rotated",
            session_id=session_id,
            credentials_id=credentials.id,
        )

        cookies.set_refresh_token_cookie(response, new_raw_refresh_token)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def activate_account(
        response: Response,
        db_session: AsyncSession,
        payload: ActivateAccount,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResponse:
        settings = get_settings()

        activation_token_hash = sha256(payload.activation_token)

        credentials = await AuthRepository.get_credentials_by_activation_token_hash(
            db_session, activation_token_hash
        )
        if credentials is None or credentials.activation is None:
            logger.warning(
                "activation_failed",
                reason="activation_token_not_found",
            )

            raise exceptions.InvalidActivationTokenError()

        if datetime.now(UTC) > credentials.activation.activation_token_expires_at:
            logger.warning(
                "activation_failed",
                credentials_id=credentials.id,
                failure_reason="activation_token_expired",
            )

            raise exceptions.ExpiredActivationTokenError()

        if credentials.status != UserStatus.PENDING_ACTIVATION:
            logger.warning(
                "activation_failed",
                credentials_id=credentials.id,
                status=credentials.status,
                failure_reason="wrong_user_status",
            )

            raise UserNotPendingActivationError()

        claimed = await AuthRepository.claim_activation_token(
            db_session, credentials.id
        )

        if not claimed:
            logger.warning(
                "activation_failed",
                credentials_id=credentials.id,
                failure_reason="concurrent_claim",
            )

            raise exceptions.InvalidActivationTokenError()

        credentials.password_hash = await hash_password(payload.new_password)
        credentials.status = UserStatus.ACTIVE

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

        await db_session.commit()

        send_email_in_background(
            send_account_activated_email(to_email=credentials.email),
            email_type=EmailType.ACCOUNT_ACTIVATED,
        )

        logger.info(
            "account_activated",
            credentials_id=credentials.id,
            role=credentials.role,
            session_id=user_session.id,
        )

        cookies.set_refresh_token_cookie(response, raw_refresh_token)
        cookies.set_device_id_cookie(response, device_id)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def request_password_reset(
        db_session: AsyncSession,
        payload: PasswordResetRequestPublic,
    ) -> None:
        settings = get_settings()

        raw_reset_password_token, hashed_reset_password_token = generate_token()

        credentials = await UserCredentialsRepository.get_by_username(
            db_session,
            payload.username,
            load_options=LoadOptionsSchema(
                load_login_lockout=True,
                load_password_reset=True,
            ),
        )
        if credentials is None:
            logger.info(
                "password_reset_request_failed",
                username=payload.username,
                failure_reason="user_not_found",
            )

            return

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_ACTIVATION,
        ):
            logger.info(
                "password_reset_request_failed",
                credentials_id=credentials.id,
                failure_reason=f"status_{credentials.status.value}",
            )

            return

        if credentials.password_reset is None:
            new_password_reset = UserPasswordReset(
                credentials_id=credentials.id,
                reset_password_token_hash=hashed_reset_password_token,
                reset_password_token_expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.RESET_PASSWORD_EXPIRES_MINUTES),
            )

            db_session.add(new_password_reset)
        else:
            credentials.password_reset.reset_password_token_hash = (
                hashed_reset_password_token
            )
            credentials.password_reset.reset_password_token_expires_at = datetime.now(
                UTC
            ) + timedelta(minutes=settings.RESET_PASSWORD_EXPIRES_MINUTES)

        subject, html_body = build_reset_password_email(raw_reset_password_token)

        db_session.add(
            Email(
                recipient_email=credentials.email,
                subject=subject,
                html_body=html_body,
                email_type=EmailType.PUBLIC_PASSWORD_RESET,
            )
        )

        await db_session.commit()

        logger.info(
            "password_reset_requested",
            credentials_id=credentials.id,
        )

    @staticmethod
    async def reset_password(
        db_session: AsyncSession,
        redis: Redis,
        payload: ResetPassword,
    ) -> None:
        reset_password_token_hash = sha256(payload.reset_password_token)

        credentials = await AuthRepository.get_credentials_by_reset_password_token_hash(
            db_session, reset_password_token_hash
        )
        if credentials is None or credentials.password_reset is None:
            logger.warning(
                "reset_password_failed",
                failure_reason="reset_password_token_not_found",
            )

            raise exceptions.InvalidResetPasswordTokenError()

        if (
            datetime.now(UTC)
            > credentials.password_reset.reset_password_token_expires_at
        ):
            logger.warning(
                "reset_password_failed",
                reason="reset_token_expired",
                credentials_id=credentials.id,
            )

            raise exceptions.ExpiredResetPasswordTokenError()

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_ACTIVATION,
        ):
            logger.warning(
                "reset_password_failed",
                reason=f"status_{credentials.status.value}",
                credentials_id=credentials.id,
            )

            raise exceptions.InvalidResetPasswordTokenError()

        session_ids = await AuthRepository.get_session_ids(db_session, credentials.id)

        await AuthRepository.delete_all_sessions(db_session, credentials.id)
        await AuthRepository.delete_reset_password_record(db_session, credentials.id)

        credentials.password_hash = await hash_password(payload.new_password)

        if credentials.login_lockout is not None:
            credentials.login_lockout.failed_attempts = 0
            credentials.login_lockout.locked_until = None
            credentials.login_lockout.last_failed_at = None

        db_session.add(
            LoginHistory(
                credentials_id=credentials.id,
                success=True,
                ip_address=None,
                user_agent=None,
                failure_reason="password_reset",
            )
        )

        await delete_cache_critical(
            redis,
            *[
                SessionCacheKey.access_token_version_key(session_id)
                for session_id in session_ids
            ],
        )

        await db_session.commit()

        send_email_in_background(
            send_password_changed_confirmation(credentials.email),
            email_type=EmailType.PASSWORD_CHANGE_CONFIRMATION,
        )

        logger.info(
            "password_reset_completed",
            credentials_id=credentials.id,
            sessions_revoked=len(session_ids),
        )
