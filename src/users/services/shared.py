import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.advisory_locks import acquire_contact_locks
from src.core.caching import delete_cache, get_cache, set_cache
from src.core.config import get_settings
from src.core.dependencies import CurrentUser
from src.core.security import (
    generate_email_change_code,
    hash_password,
    verify_email_change_code,
    verify_password,
)
from src.emails.utils.enums import EmailType
from src.users.repository.user import UserCredentialsRepository, UserRepositoryBase
from src.users.schemas.shared import (
    ConfirmEmailChange,
    UpdateMePassword,
    UpdateUserCredentials,
    UserResponseSelf,
)
from src.users.utils.constants import STUDENT_ROLE
from src.users.utils.enums import UserRole
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    DuplicateEmailChangeRequestError,
    EmailChangeCodeExpiredError,
    IncorrectPasswordError,
    InvalidEmailChangeCodeError,
    NoPendingEmailChangeError,
    UserNotFoundError,
    handle_non_student_unique_contact_error,
    handle_username_integrity_error,
)
from src.users.utils.helpers import check_contact_limit
from src.users.utils.schemas import LoadOptionsSchema
from src.utils import email as emails
from src.utils.cache_keys import SessionCacheKey, UserCacheKey
from src.utils.exceptions import NoChangesDetectedError, raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)


class UserServiceSelf:
    @staticmethod
    async def get_my_profile(
        session: AsyncSession, redis: Redis, current_user: CurrentUser
    ) -> UserResponseSelf:
        cache_key = UserCacheKey.user_detail_key_self(current_user.id)
        cached = await get_cache(redis, cache_key)

        if cached is not None:
            return UserResponseSelf.model_validate(cached)

        user = await UserRepositoryBase.get_user_by_public_id(
            session,
            current_user.public_id,
            allowed_roles=STUDENT_ROLE,
        )
        if user is None:
            raise UserNotFoundError()

        response = UserResponseSelf.model_validate(user)

        await set_cache(redis, cache_key, response.model_dump(mode="json"), 900)

        return response

    @staticmethod
    async def update_me_credentials(
        session: AsyncSession,
        redis: Redis,
        current_user: CurrentUser,
        update_request: UpdateUserCredentials,
    ) -> None:
        target_user = await UserCredentialsRepository.get_by_public_id(
            session,
            current_user.public_id,
            load_options=LoadOptionsSchema(
                load_sessions=True,
                load_email_change=True,
            ),
        )
        if target_user is None:
            raise CredentialsNotFoundError()

        user_with_session = target_user.sessions

        username_changing = (
            update_request.username is not None
            and update_request.username != target_user.username
        )
        email_requested = (
            update_request.email is not None
            and update_request.email != target_user.email
        )

        if not username_changing and not email_requested:
            raise NoChangesDetectedError()

        if email_requested:
            pending_still_active = (
                user_with_session.email_change_code_expires_at is not None
                and user_with_session.email_change_code_expires_at > datetime.now(UTC)
            )

            if (
                user_with_session.pending_new_email == update_request.email
                and pending_still_active
            ):
                logger.warning(
                    "email_change_request_denied",
                    public_id=current_user.public_id,
                    denial_reason="duplicate_pending_request",
                )

                raise DuplicateEmailChangeRequestError()

        try:
            if username_changing:
                target_user.username = update_request.username
                target_user.session.access_token_version += 1

            if email_requested:
                raw_code, hashed_code = generate_email_change_code()
                code_expires_at = datetime.now(UTC) + timedelta(
                    minutes=get_settings().EMAIL_CHANGE_CODE_EXPIRES_MINUTES
                )

                target_user.email_change.new_email = update_request.email
                target_user.email_change.email_change_code_hash = hashed_code
                target_user.email_change.email_change_code_expires_at = code_expires_at

            await session.commit()
            await session.refresh(target_user)

            if email_requested:
                asyncio.create_task(
                    emails.send_email_safe(
                        emails.send_email_change_verification(
                            update_request.email, raw_code
                        ),
                        email_type=EmailType.EMAIL_CHANGE_CODE,
                    )
                )

            await delete_cache(
                redis,
                UserCacheKey.user_detail_key_admin(target_user.id),
                UserCacheKey.user_detail_key_staff(target_user.id),
                UserCacheKey.user_detail_key_self(target_user.id),
            )

            if username_changing:
                await delete_cache(
                    redis,
                    SessionCacheKey.access_token_version_key(target_user.id),
                )

                logger.info(
                    "username_updated",
                    target_user_id=current_user.public_id,
                    new_username=target_user.username,
                    method="self_service",
                )

            if email_requested:
                logger.info(
                    "user_email_update_requested",
                    target_user_id=current_user.public_id,
                    email_change_requested=target_user.email,
                    method="self_service",
                )

        except IntegrityError as exc:
            await session.rollback()

            logger.error(
                "user_credentials_update_failed",
                target_user_id=current_user.public_id,
                reason=str(exc.orig),
                method="self_service",
            )

            handle_username_integrity_error(exc)
            raise_unhandled_integrity_error(exc)

    @staticmethod
    async def confirm_email_change(
        session: AsyncSession,
        redis: Redis,
        current_user: CurrentUser,
        confirm_request: ConfirmEmailChange,
    ) -> None:
        target_user = await UserCredentialsRepository.get_by_public_id(
            session,
            current_user.public_id,
            load_options=LoadOptionsSchema(
                load_sessions=True,
                load_login_lockout=True,
            ),
        )
        if target_user is None:
            CredentialsNotFoundError()

        user_with_session = target_user.sessions
        if (
            user_with_session.pending_new_email is None
            or user_with_session.email_change_code_hash is None
        ):
            raise NoPendingEmailChangeError()

        if user_with_session.email_change_code_expires_at < datetime.now(UTC):
            raise EmailChangeCodeExpiredError()

        if not verify_email_change_code(
            confirm_request.code, user_with_session.email_change_code_hash
        ):
            logger.warning(
                "email_change_confirmation_denied",
                target_user_id=current_user.public_id,
                denial_reason="invalid_code",
            )

            raise InvalidEmailChangeCodeError("Invalid email change code")

        new_email = target_user.email_change.new_email
        is_student = target_user.role == UserRole.STUDENT

        if is_student:
            await acquire_contact_locks(session, phone_number=None, email=new_email)

            await check_contact_limit(
                session,
                current_user.credentials_id,
                username=target_user.username,
                phone_number=None,
                email=new_email,
                role=UserRole.STUDENT,
                resolved_role=UserRole.STUDENT,
                exclude_user_id=current_user.credentials_id,
            )

        try:
            old_email = target_user.email
            target_user.email = new_email

            target_user.email_change.new_email = None
            target_user.email_change.email_change_code_hash = None
            target_user.email_change.email_change_code_expires_at = None

            for session_row in target_user.sessions:
                session_row.access_token_version += 1
                session_row.refresh_token_hash = None
                session_row.refresh_token_family = None
                session_row.refresh_token_expires_at = None

            await session.commit()
            await session.refresh(target_user)

            asyncio.create_task(
                emails.send_email_safe(
                    emails.send_email_changed_notification(
                        target_user.email, old_email, target_user.email
                    ),
                    email_type=EmailType.EMAIL_CHANGED,
                )
            )

            await delete_cache(
                redis,
                SessionCacheKey.access_token_version_key(current_user.public_id),
                UserCacheKey.user_detail_key_admin(current_user.public_id),
                UserCacheKey.user_detail_key_staff(current_user.public_id),
                UserCacheKey.user_detail_key_self(current_user.public_id),
            )

            logger.info(
                "email_changed",
                target_user_id=current_user.public_id,
                method="self_service",
            )

        except IntegrityError as exc:
            await session.rollback()

            logger.error(
                "email_change_confirmation_failed",
                target_user_id=current_user.public_id,
                reason=str(exc.orig),
                method="self_service",
            )

            if not is_student:
                handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)

    @staticmethod
    async def update_me_password(
        session: AsyncSession,
        redis: Redis,
        current_user: CurrentUser,
        update_request: UpdateMePassword,
    ) -> None:
        target_user = await UserCredentialsRepository.get_by_public_id(
            session,
            current_user.public_id,
            load_options=LoadOptionsSchema(load_sessions=True),
        )
        if target_user is None:
            CredentialsNotFoundError()

        is_current_password_valid = await verify_password(
            update_request.current_password, target_user.password_hash
        )

        if not is_current_password_valid:
            logger.warning(
                "password_change_denied",
                target_user_id=current_user.public_id,
                denial_reason="incorrect_current_password",
                method="self_service",
            )

            raise IncorrectPasswordError()

        new_password_hash = await hash_password(update_request.new_password)

        target_user.password_hash = new_password_hash

        for session_row in target_user.sessions:
            session_row.access_token_version += 1
            session_row.refresh_token_hash = None
            session_row.refresh_token_family = None
            session_row.refresh_token_expires_at = None

        await session.commit()

        asyncio.create_task(
            emails.send_email_safe(
                emails.send_password_changed_notification(target_user.email),
                email_type=EmailType.PASSWORD_CHANGED,
            )
        )

        await delete_cache(
            redis,
            SessionCacheKey.access_token_version_key(current_user.public_id),
        )

        logger.info(
            "password_changed",
            target_user_id=current_user.public_id,
            method="self_service",
        )
