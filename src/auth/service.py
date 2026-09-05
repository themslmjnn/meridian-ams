import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import structlog
from fastapi import Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import AuthRepository
from src.auth.schemas import (
    ActivateAccount,
    CreateAccessToken,
    CreateRefreshToken,
    ForgotPasswordRequest,
    LoginResponse,
    ResetPasswordRequest,
)
from src.core.caching import delete_cache, get_redis, set_cache_critical
from src.core.config import get_settings
from src.core.dependencies import CurrentUser
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_reset_password_token,
    hash_password,
    verify_password,
    verify_token,
)
from src.emails.models import Email
from src.emails.utils.enums import EmailType
from src.users.models.login_history import LoginHistory
from src.users.models.password_reset import UserPasswordReset
from src.users.models.session import UserSession
from src.users.repository.user import UserCredentialsRepository, UserSessionRepository
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import UserNotPendingActivationError
from src.users.utils.schemas import LoadOptionsSchema
from src.utils.cache_keys import SessionCacheKey
from src.utils.email import build_reset_password_email
from src.utils.exceptions import (
    AccessDeniedError,
    AccountInactiveError,
    AccountLockedError,
    ExpiredActivationCodeError,
    ExpiredRefreshTokenError,
    ExpiredResetPasswordTokenError,
    GracePeriodExpiredError,
    InvalidActivationCodeError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidResetPasswordTokenError,
)

logger = structlog.get_logger(__name__)

_COOKIE_PATH_REFRESH = "/api/v1/auth/refresh-token"
_COOKIE_PATH_LOGIN = "/api/v1/auth/login"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
_SESSION_CAP = 10


class AuthService:
    @staticmethod
    def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
        response.set_cookie(
            key="refresh_token",
            value=raw_refresh_token,
            httponly=True,
            secure=get_settings().COOKIE_SECURE,
            samesite="strict",
            max_age=_COOKIE_MAX_AGE,
            path=_COOKIE_PATH_REFRESH,
        )

    @staticmethod
    def _clear_refresh_cookie(response: Response) -> None:
        response.delete_cookie(
            key="refresh_token",
            path=_COOKIE_PATH_REFRESH,
        )

    @staticmethod
    def _set_refresh_family_cookie(response: Response, raw_family: str) -> None:
        response.set_cookie(
            key="refresh_token_family",
            value=raw_family,
            httponly=True,
            secure=get_settings().COOKIE_SECURE,
            samesite="strict",
            max_age=_COOKIE_MAX_AGE,
            path=_COOKIE_PATH_REFRESH,
        )

    @staticmethod
    def _clear_refresh_family_cookie(response: Response) -> None:
        response.delete_cookie(
            key="refresh_token_family",
            path=_COOKIE_PATH_REFRESH,
        )

    @staticmethod
    def _set_device_id_cookie(response: Response, device_id: str) -> None:
        response.set_cookie(
            key="device_id",
            value=device_id,
            httponly=True,
            secure=get_settings().COOKIE_SECURE,
            samesite="strict",
            max_age=_COOKIE_MAX_AGE,
            path=_COOKIE_PATH_LOGIN,
        )

    @staticmethod
    def _clear_device_id_cookie(response: Response) -> None:
        response.delete_cookie(
            key="device_id",
            path=_COOKIE_PATH_LOGIN,
        )

    @staticmethod
    async def login(
        response: Response,
        request: Request,
        session: AsyncSession,
        form_data: OAuth2PasswordRequestForm,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResponse:

        credentials = await UserCredentialsRepository.get_by_username(
            session,
            form_data.username,
            load_options=LoadOptionsSchema(load_login_lockout=True),
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
                credentials_id=credentials.id,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="account_not_activated",
            )

            session.add(new_login_history)
            await session.commit()

            raise AccountInactiveError()

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_DELETION,
        ):
            new_login_history = LoginHistory(
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

            if lockout.failed_attempts >= get_settings()().MAX_FAILED_LOGIN_ATTEMPTS:
                lockout.locked_until = datetime.now(UTC) + timedelta(
                    minutes=get_settings()().LOCKOUT_DURATION_MINUTES
                )

                logger.warning(
                    "account_locked",
                    credentials_id=credentials.id,
                    failed_attempts=lockout.failed_attempts,
                    locked_until=lockout.locked_until.isoformat(),
                )

            new_login_history = LoginHistory(
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

        incoming_device_id = request.cookies.get("device_id")
        existing_session = None

        if incoming_device_id:
            existing_session = await AuthRepository.get_session_by_device_id(
                session,
                credentials_id=credentials.id,
                device_id=incoming_device_id,
            )

        if existing_session is not None:
            # Known device — rotate tokens on existing session row
            device_id = incoming_device_id
            refresh_token_family = secrets.token_urlsafe(32)

            raw_refresh_token, hashed_refresh_token = create_refresh_token(
                CreateRefreshToken(
                    public_id=credentials.public_id,
                    session_id=existing_session.id,
                )
            )

            existing_session.refresh_token_hash = hashed_refresh_token
            existing_session.refresh_token_family = refresh_token_family
            existing_session.refresh_token_expires_at = datetime.now(UTC) + timedelta(
                days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS
            )
            existing_session.previous_refresh_token_hash = None
            existing_session.rotated_at = None
            existing_session.ip_address = ip_address
            existing_session.user_agent = user_agent
            existing_session.last_active_at = datetime.now(UTC)

            await session.flush()

            user_session = existing_session

        else:
            session_count = await AuthRepository.get_session_count(
                session, credentials.id
            )
            if session_count >= _SESSION_CAP:
                await AuthRepository.evict_oldest_session(session, credentials.id)

                logger.info(
                    "session_evicted",
                    credentials_id=credentials.id,
                    reason="session_cap_reached",
                    cap=_SESSION_CAP,
                )

            device_id = secrets.token_urlsafe(32)
            refresh_token_family = secrets.token_urlsafe(32)

            user_session = UserSession(
                credentials_id=credentials.id,
                refresh_token_hash="",  # set below after flush gives us session.id
                refresh_token_family=refresh_token_family,
                refresh_token_expires_at=datetime.now(UTC)
                + timedelta(days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS),
                user_agent=user_agent,
                ip_address=ip_address,
                device_id=device_id,
            )

            raw_refresh_token, hashed_refresh_token = create_refresh_token(
                CreateRefreshToken(
                    public_id=credentials.public_id,
                    session_id=user_session.id,
                )
            )

            user_session.refresh_token_hash = hashed_refresh_token

        access_token = create_access_token(
            CreateAccessToken(
                public_id=credentials.public_id,
                role=credentials.role,
                account_type=credentials.account_type,
                session_id=user_session.id,
                access_token_version=user_session.access_token_version,
            )
        )

        new_login_history = LoginHistory(
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
            session_id=user_session.id,
            device="existing" if existing_session else "new",
        )

        AuthService._set_refresh_cookie(response, raw_refresh_token)
        AuthService._set_refresh_family_cookie(response, refresh_token_family)
        AuthService._set_device_id_cookie(response, device_id)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def logout(
        session: AsyncSession,
        redis: Redis,
        response: Response,
        current_user: CurrentUser,
    ) -> None:
        user_session = await UserSessionRepository.get_by_id(
            session, current_user.session_id
        )

        if user_session is not None:
            await AuthRepository.delete_session(session, user_session)
            await session.commit()

        await delete_cache(redis, SessionCacheKey(current_user.session_id))

        AuthService._clear_refresh_cookie(response)
        AuthService._clear_refresh_family_cookie(response)

        logger.info(
            "logout",
            credentials_id=current_user.credentials_id,
            session_id=current_user.session_id,
        )

    @staticmethod
    async def logout_all(
        session: AsyncSession,
        redis: Redis,
        response: Response,
        current_user: CurrentUser,
    ) -> None:
        # Fetch all session IDs before deleting — needed for cache invalidation
        session_ids = await AuthRepository.get_session_ids(
            session, current_user.credentials_id
        )

        await AuthRepository.delete_all_sessions(session, current_user.credentials_id)
        await session.commit()

        for session_id in session_ids:
            await delete_cache(
                redis, SessionCacheKey.access_token_version_key(session_id)
            )

        AuthService._clear_refresh_cookie(response)
        AuthService._clear_refresh_family_cookie(response)
        AuthService._clear_device_id_cookie(response)

        logger.info(
            "logout_all",
            credentials_id=current_user.credentials_id,
            sessions_revoked=len(session_ids),
        )

    @staticmethod
    async def refresh_token(
        request: Request,
        response: Response,
        session: AsyncSession,
        raw_refresh_token: str,
        raw_refresh_family: str,
    ) -> LoginResponse:
        try:
            payload = decode_refresh_token(raw_refresh_token)
            session_id = int(payload["session_id"])

        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "refresh_failed",
                reason="invalid_jwt",
            )

            raise InvalidRefreshTokenError() from exc

        user_session = await AuthRepository.get_session_by_id(session, session_id)

        if (
            user_session is None
            or user_session.refresh_token_hash is None
            or user_session.refresh_token_family is None
            or user_session.refresh_token_expires_at is None
        ):
            logger.warning(
                "refresh_failed",
                reason="session_not_found_or_incomplete",
                session_id=session_id,
            )

            raise InvalidRefreshTokenError()

        # --- 3. Check refresh token expiry ---
        if datetime.now(UTC) > user_session.refresh_token_expires_at:
            logger.warning(
                "refresh_failed",
                reason="refresh_token_expired",
                session_id=session_id,
            )

            raise ExpiredRefreshTokenError()

        family_valid = verify_token(
            raw_refresh_family,
            user_session.refresh_token_family,
        )

        token_matches_current = verify_token(
            raw_refresh_token,
            user_session.refresh_token_hash,
        )

        token_matches_previous = (
            user_session.previous_refresh_token_hash is not None
            and verify_token(
                raw_refresh_token,
                user_session.previous_refresh_token_hash,
            )
        )

        if not family_valid or (
            not token_matches_current and not token_matches_previous
        ):
            await AuthRepository.invalidate_session_family(session, user_session)
            await session.commit()

            await delete_cache(
                get_redis(request), SessionCacheKey.access_token_version_key(session_id)
            )

            logger.warning(
                "refresh_security_violation",
                session_id=session_id,
                family_valid=family_valid,
                token_matches_current=token_matches_current,
                token_matches_previous=token_matches_previous,
                action="session_invalidated",
            )

            raise InvalidRefreshTokenError()

        if token_matches_previous and not token_matches_current:
            grace_window = timedelta(
                seconds=get_settings().REFRESH_GRACE_WINDOW_SECONDS
            )
            within_grace = (
                user_session.rotated_at is not None
                and datetime.now(UTC) - user_session.rotated_at < grace_window
            )

            if within_grace:
                # Second tab raced — return the already-rotated token
                # that's sitting in their cookie from the first request.
                # We can't re-send the raw token (we don't store it),
                # so we issue a fresh access token against the current session state.
                credentials = await UserCredentialsRepository.get_by_id(
                    session, user_session.credentials_id
                )

                access_token = create_access_token(
                    CreateAccessToken(
                        public_id=credentials.public_id,
                        role=credentials.role,
                        account_type=credentials.account_type,
                        session_id=user_session.id,
                        access_token_version=user_session.access_token_version,
                    )
                )

                logger.info(
                    "refresh_grace_window_hit",
                    session_id=session_id,
                )
                # Cookies already set from the first rotation — don't overwrite
                return LoginResponse(access_token=access_token, token_type="bearer")

            else:
                # Previous token used outside grace window — replay attack
                await AuthRepository.invalidate_session_family(session, user_session)
                await session.commit()

                await delete_cache(
                    get_redis(request),
                    SessionCacheKey.access_token_version_key(session_id),
                )

                logger.warning(
                    "refresh_replay_attack",
                    session_id=session_id,
                    rotated_at=user_session.rotated_at.isoformat()
                    if user_session.rotated_at
                    else None,
                    action="session_invalidated",
                )

                raise InvalidRefreshTokenError()

        credentials = await UserCredentialsRepository.get_by_id(
            session, user_session.credentials_id
        )

        if credentials is None:
            raise InvalidRefreshTokenError()

        new_family = secrets.token_urlsafe(32)
        raw_new_refresh_token, hashed_new_refresh_token = create_refresh_token(
            CreateRefreshToken(
                public_id=credentials.public_id,
                session_id=user_session.id,
            )
        )

        user_session.previous_refresh_token_hash = user_session.refresh_token_hash
        user_session.rotated_at = datetime.now(UTC)
        user_session.refresh_token_hash = hashed_new_refresh_token
        user_session.refresh_token_family = new_family
        user_session.refresh_token_expires_at = datetime.now(UTC) + timedelta(
            days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS
        )
        user_session.last_active_at = datetime.now(UTC)

        access_token = create_access_token(
            CreateAccessToken(
                public_id=credentials.public_id,
                role=credentials.role,
                account_type=credentials.account_type,
                session_id=user_session.id,
                access_token_version=user_session.access_token_version,
            )
        )

        await session.commit()

        # Refresh ATV cache with current version + TTL reset
        await set_cache_critical(
            get_redis(request),
            SessionCacheKey.access_token_version_key(session_id),
            SessionCacheKey.pack_atv_cache(
                user_session.access_token_version, credentials.id
            ),
            ex=get_settings().ACCESS_TOKEN_EXPIRES_MINUTES * 60,
        )

        logger.info(
            "refresh_token_rotated",
            session_id=session_id,
            credentials_id=credentials.id,
        )

        AuthService._set_refresh_cookie(response, raw_new_refresh_token)
        AuthService._set_refresh_family_cookie(response, new_family)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def activate_account(
        response: Response,
        session: AsyncSession,
        payload: ActivateAccount,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResponse:
        token_hash = sha256(payload.token)

        credentials = await AuthRepository.get_credentials_by_activation_token_hash(
            session, token_hash
        )

        if credentials is None or credentials.activation is None:
            logger.warning("activation_failed", reason="token_not_found")

            raise InvalidActivationCodeError()

        if datetime.now(UTC) > credentials.activation.activation_token_expires_at:
            logger.warning(
                "activation_failed",
                reason="token_expired",
                credentials_id=credentials.id,
            )

            raise ExpiredActivationCodeError()

        if credentials.status != UserStatus.PENDING_ACTIVATION:
            logger.warning(
                "activation_failed",
                reason="wrong_status",
                credentials_id=credentials.id,
                status=credentials.status,
            )

            raise UserNotPendingActivationError()

        claimed = await AuthRepository.claim_activation_token(session, credentials.id)

        if not claimed:
            # Another concurrent request got here first
            logger.warning(
                "activation_failed",
                reason="concurrent_claim",
                credentials_id=credentials.id,
            )

            raise InvalidActivationCodeError()

        credentials.password_hash = await hash_password(payload.password)
        credentials.status = UserStatus.ACTIVE

        refresh_token_family = secrets.token_urlsafe(32)
        device_id = secrets.token_urlsafe(32)

        user_session = await UserSession(
            credentials_id=credentials.id,
            refresh_token_hash="",
            refresh_token_family=refresh_token_family,
            refresh_token_expires_at=datetime.now(UTC)
            + timedelta(days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
            device_id=device_id,
        )

        raw_refresh_token, hashed_refresh_token = create_refresh_token(
            CreateRefreshToken(
                public_id=credentials.public_id,
                session_id=user_session.id,
            )
        )
        user_session.refresh_token_hash = hashed_refresh_token

        access_token = create_access_token(
            CreateAccessToken(
                public_id=credentials.public_id,
                role=credentials.role,
                account_type=credentials.account_type,
                session_id=user_session.id,
                access_token_version=user_session.access_token_version,
            )
        )

        await session.commit()

        logger.info(
            "account_activated",
            credentials_id=credentials.id,
            role=credentials.role,
            session_id=user_session.id,
        )

        AuthService._set_refresh_cookie(response, raw_refresh_token)
        AuthService._set_refresh_family_cookie(response, refresh_token_family)
        AuthService._set_device_id_cookie(response, device_id)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def forgot_password(
        session: AsyncSession,
        payload: ForgotPasswordRequest,
    ) -> None:
        # Always hash regardless of whether email exists —
        # keeps response time consistent, prevents email enumeration
        raw_token, token_hash = generate_reset_password_token()

        credentials = await UserCredentialsRepository.get_by_email(
            session,
            payload.email,
            load_options=LoadOptionsSchema(
                load_login_lockout=True,
                load_password_reset=True,
            ),
        )

        if credentials is None:
            logger.info(
                "forgot_password_email_not_found",
                reason="no_account_for_email",
            )
            # Return silently — never reveal whether email exists
            return

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_ACTIVATION,
        ):
            logger.info(
                "forgot_password_skipped",
                credentials_id=credentials.id,
                reason=f"status_{credentials.status.value}",
            )

            return

        expires_at = datetime.now(UTC) + timedelta(
            minutes=get_settings().RESET_PASSWORD_TOKEN_EXPIRES_MINUTES
        )

        if credentials.password_reset is None:
            new_password_reset = UserPasswordReset(
                credentials_id=credentials.id,
                reset_password_token_hash=token_hash,
                reset_password_token_expires_at=datetime.now(UTC)
                + timedelta(minutes=get_settings().RESET_PASSWORD_EXPIRES_MINUTES),
            )

            session.add(new_password_reset)
        else:
            credentials.password_reset.reset_password_token_hash = token_hash
            credentials.password_reset.reset_password_token_expires_at = datetime.now(
                UTC
            ) + timedelta(minutes=get_settings().RESET_PASSWORD_EXPIRES_MINUTES)

        subject, html_body = build_reset_password_email(raw_token)

        new_email = Email(
            recipient_email=credentials.email,
            subject=subject,
            body_html=html_body,
            email_type=EmailType.PASSWORD_RESET_ADMIN,
        )

        session.add(new_email)
        await session.commit()

        logger.info(
            "forgot_password_token_issued",
            credentials_id=credentials.id,
        )

    @staticmethod
    async def reset_password(
        request: Request,
        session: AsyncSession,
        payload: ResetPasswordRequest,
    ) -> None:
        token_hash = sha256(payload.token)

        credentials = await AuthRepository.get_credentials_by_reset_token_hash(
            session, token_hash
        )

        if credentials is None or credentials.password_reset is None:
            logger.warning("reset_password_failed", reason="token_not_found")

            raise InvalidResetPasswordTokenError()

        if (
            datetime.now(UTC)
            > credentials.password_reset.reset_password_token_expires_at
        ):
            logger.warning(
                "reset_password_failed",
                reason="token_expired",
                credentials_id=credentials.id,
            )

            raise ExpiredResetPasswordTokenError()

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_ACTIVATION,
        ):
            logger.warning(
                "reset_password_failed",
                reason=f"status_{credentials.status.value}",
                credentials_id=credentials.id,
            )

            raise InvalidResetPasswordTokenError()

        session_ids = await AuthRepository.get_all_session_ids(session, credentials.id)

        await AuthRepository.delete_all_sessions(session, credentials.id)

        await AuthRepository.delete_password_reset_token(session, credentials.id)

        credentials.password_hash = await hash_password(payload.new_password)

        if credentials.login_lockout is not None:
            credentials.login_lockout.failed_attempts = 0
            credentials.login_lockout.locked_until = None
            credentials.login_lockout.last_failed_at = None

        new_login_history = LoginHistory(
            credentials_id=credentials.id,
            success=True,
            ip_address=None,
            user_agent=None,
            failure_reason="password_reset",
        )

        session.add(new_login_history)
        await session.commit()

        for session_id in session_ids:
            await delete_cache(
                get_redis(request), SessionCacheKey.access_token_version_key(session_id)
            )

        logger.info(
            "password_reset_complete",
            credentials_id=credentials.id,
            sessions_revoked=len(session_ids),
        )
