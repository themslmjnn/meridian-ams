import secrets
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

import src.utils.exceptions as exceptions
from src.auth.repository import AuthRepository
from src.auth.schemas import (
    ActivateAccount,
    CreateAccessToken,
    CreateRefreshToken,
    ForgotPasswordRequest,
    LoginResponse,
    ResetPasswordRequest,
)
from src.core.caching import delete_cache
from src.core.config import get_settings
from src.core.dependencies import CurrentUser, verify_status
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_token,
    hash_password,
    sha256,
    verify_password,
    verify_token,
)
from src.emails.models import Email
from src.emails.utils.enums import EmailType
from src.users.models.credentials import UserCredentials
from src.users.models.login_history import LoginHistory
from src.users.models.password_reset import UserPasswordReset
from src.users.models.session import UserSession
from src.users.repository.user import (
    UserCredentialsRepository,
    UserSessionRepository,
)
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import UserNotPendingActivationError
from src.users.utils.schemas import LoadOptionsSchema
from src.utils.cache_keys import SessionCacheKey
from src.utils.email import build_reset_password_email

logger = structlog.get_logger(__name__)

_COOKIE_PATH_REFRESH = "/api/v1/auth/refresh-token"
_COOKIE_PATH_LOGIN = "/api/v1/auth/login"


class AuthService:
    @staticmethod
    def _set_refresh_token_cookie(response: Response, raw_refresh_token: str) -> None:
        response.set_cookie(
            key="refresh_token",
            value=raw_refresh_token,
            httponly=True,
            secure=get_settings().COOKIE_SECURE,
            samesite="strict",
            max_age=get_settings().REFRESH_TOKEN_EXPIRES_DAYS,
            path=_COOKIE_PATH_REFRESH,
        )

    @staticmethod
    def _clear_refresh_token_cookie(response: Response) -> None:
        response.delete_cookie(
            key="refresh_token",
            path=_COOKIE_PATH_REFRESH,
        )

    @staticmethod
    def _set_refresh_token_family_cookie(
        response: Response, raw_refresh_token_family: str
    ) -> None:
        response.set_cookie(
            key="refresh_token_family",
            value=raw_refresh_token_family,
            httponly=True,
            secure=get_settings().COOKIE_SECURE,
            samesite="strict",
            max_age=get_settings().REFRESH_TOKEN_EXPIRES_DAYS,
            path=_COOKIE_PATH_REFRESH,
        )

    @staticmethod
    def _clear_refresh_token_family_cookie(response: Response) -> None:
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
            max_age=get_settings().REFRESH_TOKEN_EXPIRES_DAYS,
            path=_COOKIE_PATH_LOGIN,
        )

    @staticmethod
    def _clear_device_id_cookie(response: Response) -> None:
        response.delete_cookie(
            key="device_id",
            path=_COOKIE_PATH_LOGIN,
        )

    @staticmethod
    async def _revoke_session(
        session: AsyncSession,
        redis: Redis,
        user_session: UserSession,
        session_id: int,
    ) -> None:
        await AuthRepository.invalidate_session_family(session, user_session)
        await session.commit()
        await delete_cache(redis, SessionCacheKey.access_token_version_key(session_id))

    @staticmethod
    def _access_token_for(
        credentials: UserCredentials, user_session: UserSession
    ) -> str:
        return create_access_token(
            CreateAccessToken(
                public_id=credentials.public_id,
                role=credentials.role,
                account_type=credentials.account_type,
                session_id=user_session.id,
                access_token_version=user_session.access_token_version,
            )
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
            load_options=LoadOptionsSchema(
                load_identity=True,
                load_login_lockout=True,
            ),
        )
        if credentials is None:
            await verify_password(
                form_data.password,
                "$2b$12$placeholder.hash.to.keep.timing.consistent.x",
            )

            logger.warning(
                "login_failed",
                reason="user_not_found",
                username=form_data.username,
            )

            raise exceptions.InvalidCredentialsError()

        lockout = credentials.login_lockout

        if lockout.locked_until and datetime.now(UTC) < lockout.locked_until:
            session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="account_locked",
                )
            )

            await session.commit()

            logger.warning(
                "login_blocked",
                reason="account_locked",
                credentials_id=credentials.id,
                locked_until=lockout.locked_until.isoformat(),
            )

            raise exceptions.AccountLockedError(
                detail=f"Account locked until {lockout.locked_until.strftime('%H:%M UTC')}"
            )

        if credentials.status == UserStatus.PENDING_ACTIVATION:
            session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="account_not_activated",
                )
            )

            await session.commit()

            raise exceptions.AccountInactiveError()

        if credentials.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_DELETION,
        ):
            session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason=f"account_{credentials.status.value}",
                )
            )

            await session.commit()

            raise exceptions.AccessDeniedError()

        if not await verify_password(
            form_data.password, credentials.password_hash or ""
        ):
            lockout.failed_attempts += 1
            lockout.last_failed_at = datetime.now(UTC)

            if lockout.failed_attempts >= get_settings().MAX_LOGIN_ATTEMPTS:
                lockout.locked_until = datetime.now(UTC) + timedelta(
                    minutes=get_settings().LOCKOUT_DURATION_MINUTES
                )

                logger.warning(
                    "account_locked",
                    credentials_id=credentials.id,
                    failed_attempts=lockout.failed_attempts,
                    locked_until=lockout.locked_until.isoformat(),
                )

            session.add(
                LoginHistory(
                    credentials_id=credentials.id,
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="invalid_password",
                )
            )

            await session.commit()

            logger.warning(
                "login_failed",
                reason="invalid_password",
                credentials_id=credentials.id,
                failed_attempts=lockout.failed_attempts,
            )

            raise exceptions.InvalidCredentialsError()

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

                raise exceptions.InvalidCredentialsError()

            credentials.status = credentials.pre_transition_status
            credentials.deletion_scheduled_for = None

            logger.info(
                "deletion_implicitly_cancelled",
                credentials_id=credentials.id,
            )

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
            device_id = incoming_device_id
            raw_refresh_token_family, hashed_refresh_token_family = generate_token()

            raw_refresh_token, hashed_refresh_token = create_refresh_token(
                CreateRefreshToken(
                    public_id=credentials.public_id,
                    session_id=existing_session.id,
                )
            )

            existing_session.refresh_token_hash = hashed_refresh_token
            existing_session.refresh_token_family_hash = hashed_refresh_token_family
            existing_session.refresh_token_expires_at = datetime.now(UTC) + timedelta(
                days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS
            )
            existing_session.ip_address = ip_address
            existing_session.user_agent = user_agent
            existing_session.last_active_at = datetime.now(UTC)

            await session.flush()

            user_session = existing_session

        else:
            session_count = await AuthRepository.get_session_count(
                session, credentials.id
            )
            if session_count >= get_settings().MAX_SESSIONS_PER_USER:
                await AuthRepository.evict_oldest_session(session, credentials.id)

                logger.info(
                    "session_evicted",
                    credentials_id=credentials.id,
                    reason="session_cap_reached",
                    cap=get_settings().MAX_SESSIONS_PER_USER,
                )

            device_id = secrets.token_urlsafe(32)
            raw_refresh_token_family, hashed_refresh_token_family = generate_token()

            user_session = UserSession(
                credentials_id=credentials.id,
                refresh_token_hash="",  # set below after flush gives us session.id
                refresh_token_family_hash=hashed_refresh_token_family,
                refresh_token_expires_at=datetime.now(UTC)
                + timedelta(days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS),
                user_agent=user_agent,
                ip_address=ip_address,
                device_id=device_id,
            )

            session.add(user_session)
            await session.flush()

            raw_refresh_token, hashed_refresh_token = create_refresh_token(
                CreateRefreshToken(
                    public_id=credentials.public_id,
                    session_id=user_session.id,
                )
            )

            user_session.refresh_token_hash = hashed_refresh_token

        access_token = AuthService._access_token_for(credentials, user_session)

        session.add(
            LoginHistory(
                credentials_id=credentials.id,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await session.commit()

        logger.info(
            "user_logged_in",
            credentials_id=credentials.id,
            role=credentials.role,
            session_id=user_session.id,
            device="existing" if existing_session else "new",
        )

        AuthService._set_refresh_token_cookie(response, raw_refresh_token)
        AuthService._set_refresh_token_family_cookie(response, raw_refresh_token_family)
        AuthService._set_device_id_cookie(response, device_id)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def logout(
        response: Response,
        session: AsyncSession,
        redis: Redis,
        current_user: CurrentUser,
    ) -> None:
        user_session = await UserSessionRepository.get_by_id(
            session, current_user.session_id
        )
        if user_session is not None:
            await session.delete(user_session)
            await session.commit()

        await delete_cache(
            redis, SessionCacheKey.access_token_version_key(current_user.session_id)
        )

        AuthService._clear_refresh_token_cookie(response)
        AuthService._clear_refresh_token_family_cookie(response)

        logger.info(
            "user_logged_out",
            credentials_id=current_user.credentials_id,
            session_id=current_user.session_id,
        )

    @staticmethod
    async def refresh_token(
        response: Response,
        session: AsyncSession,
        redis: Redis,
        raw_refresh_token: str,
        raw_refresh_token_family: str,
    ) -> LoginResponse:
        settings = get_settings()
        now = datetime.now(UTC)

        try:
            payload = decode_refresh_token(raw_refresh_token)
            session_id = int(payload["session_id"])

        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "refresh_failed",
                reason="invalid_jwt",
                error=str(exc),
            )

            raise exceptions.InvalidRefreshTokenError() from exc

        # Row lock: concurrent refreshes for one session are serialised.
        user_session = await AuthRepository.get_session_by_id(
            session, session_id, for_update=True
        )

        if (
            user_session is None
            or user_session.refresh_token_hash is None
            or user_session.refresh_token_family_hash is None
            or user_session.refresh_token_expires_at is None
        ):
            logger.warning(
                "refresh_failed",
                reason="session_not_found_or_incomplete",
                session_id=session_id,
            )

            raise exceptions.InvalidRefreshTokenError()

        if now > user_session.refresh_token_expires_at:
            logger.warning(
                "refresh_failed",
                reason="refresh_token_expired",
                session_id=session_id,
            )

            raise exceptions.ExpiredRefreshTokenError()

        family_valid = verify_token(
            raw_refresh_token_family, user_session.refresh_token_family_hash
        )
        matches_current = verify_token(
            raw_refresh_token, user_session.refresh_token_hash
        )

        if not family_valid or not matches_current:
            await AuthService._revoke_session(session, redis, user_session, session_id)

            logger.warning(
                "refresh_security_violation",
                session_id=session_id,
                family_valid=family_valid,
                token_matches_current=matches_current,
                action="session_invalidated",
            )

            raise exceptions.InvalidRefreshTokenError()

        credentials = await UserCredentialsRepository.get_by_id(
            session, user_session.credentials_id
        )
        if credentials is None:
            raise exceptions.InvalidRefreshTokenError()

        verify_status(credentials)

        new_raw_refresh_token, new_hashed_refresh_token = create_refresh_token(
            CreateRefreshToken(
                public_id=credentials.public_id, session_id=user_session.id
            )
        )

        user_session.refresh_token_hash = new_hashed_refresh_token
        user_session.refresh_token_expires_at = now + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRES_DAYS
        )
        user_session.last_active_at = now

        access_token = AuthService._access_token_for(credentials, user_session)

        await session.commit()

        logger.info(
            "refresh_token_rotated",
            session_id=session_id,
            credentials_id=credentials.id,
        )

        AuthService._set_refresh_token_cookie(response, new_raw_refresh_token)
        AuthService._set_refresh_token_family_cookie(response, raw_refresh_token_family)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def activate_account(
        response: Response,
        session: AsyncSession,
        payload: ActivateAccount,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResponse:
        token_hash = sha256(payload.activation_token)

        credentials = await AuthRepository.get_credentials_by_activation_token_hash(
            session, token_hash
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
                reason="activation_token_expired",
                credentials_id=credentials.id,
            )

            raise exceptions.ExpiredActivationCodeError()

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
            print("error")
            logger.warning(
                "activation_failed",
                reason="concurrent_claim",
                credentials_id=credentials.id,
            )

            raise exceptions.InvalidActivationTokenError()

        credentials.password_hash = await hash_password(payload.new_password)
        credentials.status = UserStatus.ACTIVE

        raw_refresh_token_family, refresh_token_family_hash = generate_token()
        device_id = secrets.token_urlsafe(32)

        user_session = UserSession(
            credentials_id=credentials.id,
            refresh_token_hash="",
            refresh_token_family_hash=refresh_token_family_hash,
            refresh_token_expires_at=datetime.now(UTC)
            + timedelta(days=get_settings().REFRESH_TOKEN_EXPIRES_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
            device_id=device_id,
        )

        session.add(user_session)
        await session.flush()

        raw_refresh_token, hashed_refresh_token = create_refresh_token(
            CreateRefreshToken(
                public_id=credentials.public_id,
                session_id=user_session.id,
            )
        )
        user_session.refresh_token_hash = hashed_refresh_token

        access_token = AuthService._access_token_for(credentials, user_session)

        await session.commit()

        logger.info(
            "account_activated",
            credentials_id=credentials.id,
            role=credentials.role,
            session_id=user_session.id,
        )

        AuthService._set_refresh_token_cookie(response, raw_refresh_token)
        AuthService._set_refresh_token_family_cookie(response, raw_refresh_token_family)
        AuthService._set_device_id_cookie(response, device_id)

        return LoginResponse(access_token=access_token, token_type="bearer")

    @staticmethod
    async def request_password_reset(
        session: AsyncSession,
        payload: ForgotPasswordRequest,
    ) -> None:
        raw_token, token_hash = generate_token()

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
                "user_not_found",
                email=payload.email,
            )

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

        session.add(
            Email(
                recipient_email=credentials.email,
                subject=subject,
                html_body=html_body,
                email_type=EmailType.FORGOT_PASSWORD,
            )
        )
        await session.commit()

        logger.info(
            "password_reset_requested",
            credentials_id=credentials.id,
        )

    @staticmethod
    async def reset_password(
        session: AsyncSession,
        redis: Redis,
        payload: ResetPasswordRequest,
    ) -> None:
        token_hash = sha256(payload.reset_password_token)

        credentials = await AuthRepository.get_credentials_by_reset_token_hash(
            session, token_hash
        )
        if credentials is None or credentials.password_reset is None:
            logger.warning(
                "reset_password_failed",
                reason="reset_token_not_found",
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

        session_ids = await AuthRepository.get_all_session_ids(session, credentials.id)

        await AuthRepository.delete_all_sessions(session, credentials.id)
        await AuthRepository.delete_password_reset_token(session, credentials.id)

        credentials.password_hash = await hash_password(payload.new_password)

        if credentials.login_lockout is not None:
            credentials.login_lockout.failed_attempts = 0
            credentials.login_lockout.locked_until = None
            credentials.login_lockout.last_failed_at = None

        session.add(
            LoginHistory(
                credentials_id=credentials.id,
                success=True,
                ip_address=None,
                user_agent=None,
                failure_reason="password_reset",
            )
        )
        await session.commit()

        await delete_cache(
            redis,
            *[
                SessionCacheKey.access_token_version_key(session_id)
                for session_id in session_ids
            ],
        )

        logger.info(
            "password_reset_complete",
            credentials_id=credentials.id,
            sessions_revoked=len(session_ids),
        )
