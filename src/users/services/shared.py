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
from src.core.email.service import send_email_safe
from src.core.security import (
    generate_email_change_code,
    hash_password,
    verify_email_change_code,
    verify_password,
)
from src.emails.templates import account
from src.emails.utils.enums import EmailType
from src.users.models.email_change import UserEmailChange
from src.users.repository.base import UserRepositoryBase
from src.users.repository.credentials import UserCredentialsRepository
from src.users.repository.session import UserSessionRepository
from src.users.schemas.shared import (
    ConfirmEmailChange,
    UpdateMePassword,
    UpdateUserCredentials,
    UserResponseSelf,
)
from src.users.utils.constants import STUDENT_ROLE
from src.users.utils.enums import AccountType
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    DuplicateEmailChangeRequestError,
    EmailChangeCodeExpiredError,
    IncorrectPasswordError,
    InvalidEmailChangeCodeError,
    NoPendingEmailChangeError,
    SamePasswordError,
    UserNotFoundError,
    handle_non_student_unique_contact_error,
    handle_username_integrity_error,
)
from src.users.utils.helpers import check_contact_limit
from src.users.utils.schemas import LoadOptionsSchema
from src.utils.cache_keys import SessionCacheKey, UserCacheKey
from src.utils.exceptions import NoChangesDetectedError, raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)


class UserServiceSelf:
    @staticmethod
    async def get_my_profile(
        session: AsyncSession,
        redis: Redis,
        current_user: CurrentUser,
    ) -> UserResponseSelf:
        cache_key = UserCacheKey.user_detail_key_self(current_user.public_id)
        cached_data = await get_cache(redis, cache_key)

        if cached_data is not None:
            return UserResponseSelf.model_validate(cached_data)

        user = await UserRepositoryBase.get_user_by_public_id(
            session,
            current_user.public_id,
            excluded_roles=STUDENT_ROLE,
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
        payload: UpdateUserCredentials,
    ) -> None:
        credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            current_user.public_id,
            load_options=LoadOptionsSchema(
                load_sessions=True,
                load_email_change=True,
            ),
        )
        if credentials is None:
            raise CredentialsNotFoundError()

        username_changing = (
            payload.username is not None and payload.username != credentials.username
        )
        email_requested = (
            payload.email is not None and payload.email != credentials.email
        )

        if not username_changing and not email_requested:
            raise NoChangesDetectedError()

        if email_requested:
            raw_code, hashed_code = generate_email_change_code()
            code_expires_at = datetime.now(UTC) + timedelta(
                minutes=get_settings().EMAIL_CHANGE_CODE_EXPIRES_MINUTES
            )

            if credentials.email_change is None:
                new_email_change = UserEmailChange(
                    credentials_id=credentials.id,
                    new_email=payload.email,
                    email_change_token_hash=hashed_code,
                    email_change_token_expires_at=code_expires_at,
                )

                session.add(new_email_change)
            else:
                pending_still_active = (
                    credentials.email_change.email_change_code_expires_at is not None
                    and credentials.email_change.email_change_code_expires_at
                    > datetime.now(UTC)
                )
                if (
                    credentials.email_change.new_email == payload.email
                    and pending_still_active
                ):
                    logger.warning(
                        "email_change_request_denied",
                        public_id=current_user.public_id,
                        denial_reason="duplicate_pending_request",
                    )

                    raise DuplicateEmailChangeRequestError()

                credentials.email_change.new_email = payload.email
                credentials.email_change.email_change_token_hash = hashed_code
                credentials.email_change.email_change_token_expires_at = code_expires_at

        try:
            if username_changing:
                credentials.username = payload.username

                session_ids = [s.id for s in credentials.sessions]

                await UserSessionRepository.invalidate_all_sessions(
                    credentials.sessions
                )

            await session.commit()

            if email_requested:
                asyncio.create_task(
                    send_email_safe(
                        account.send_email_change_verification(payload.email, raw_code),
                        email_type=EmailType.EMAIL_CHANGE_CODE,
                    )
                )

            keys_to_delete = [
                UserCacheKey.user_detail_key_admin(current_user.public_id),
                UserCacheKey.user_detail_key_staff(current_user.public_id),
                UserCacheKey.user_detail_key_self(current_user.public_id),
            ]

            if username_changing:
                keys_to_delete.extend(
                    [
                        SessionCacheKey.access_token_version_key(sid)
                        for sid in session_ids
                    ]
                )

            await delete_cache(redis, *keys_to_delete)

            if username_changing:
                logger.info(
                    "username_updated",
                    public_id=str(current_user.public_id),
                    new_username=credentials.username,
                    method="self_service",
                )

            if email_requested:
                logger.info(
                    "email_change_requested",
                    public_id=str(current_user.public_id),
                    new_email=payload.email,
                    method="self_service",
                )

        except IntegrityError as exc:
            await session.rollback()

            logger.error(
                "credentials_update_failed",
                public_id=str(current_user.public_id),
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
        credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            current_user.public_id,
            load_options=LoadOptionsSchema(
                load_sessions=True,
                load_email_change=True,
            ),
        )
        if credentials is None:
            raise CredentialsNotFoundError()

        if (
            credentials.email_change.new_email is None
            or credentials.email_change.email_change_token_hash is None
        ):
            raise NoPendingEmailChangeError()

        if credentials.email_change.email_change_token_expires_at < datetime.now(UTC):
            raise EmailChangeCodeExpiredError()

        if not verify_email_change_code(
            confirm_request.code, credentials.email_change.email_change_token_hash
        ):
            logger.warning(
                "email_change_confirmation_denied",
                public_id=current_user.public_id,
                denial_reason="invalid_code",
            )

            raise InvalidEmailChangeCodeError()

        new_email = credentials.email_change.new_email
        is_student = credentials.account_type == AccountType.STUDENT

        await acquire_contact_locks(
            session,
            phone_number=None,
            email=new_email,
        )

        await check_contact_limit(
            session,
            current_user.credentials_id,
            username=credentials.username,
            phone_number=None,
            email=new_email,
            resolved_role=credentials.role,
            account_type=credentials.account_type,
            exclude_credentials_id=current_user.credentials_id,
        )

        try:
            old_email = credentials.email
            credentials.email = new_email

            await session.delete(credentials.email_change)

            session_ids = [s.id for s in credentials.sessions]

            await UserSessionRepository.invalidate_all_sessions(credentials.sessions)

            await session.commit()

            asyncio.create_task(
                send_email_safe(
                    account.send_email_changed_notification(
                        old_email, credentials.email
                    ),
                    email_type=EmailType.EMAIL_CHANGED,
                )
            )

            await delete_cache(
                redis,
                *[
                    SessionCacheKey.access_token_version_key(session_id)
                    for session_id in session_ids
                ],
                UserCacheKey.user_detail_key_admin(current_user.public_id),
                UserCacheKey.user_detail_key_staff(current_user.public_id),
                UserCacheKey.user_detail_key_self(current_user.public_id),
            )

            logger.info(
                "email_changed",
                credentials_id=current_user.public_id,
                method="self_service",
            )

        except IntegrityError as exc:
            await session.rollback()

            logger.error(
                "email_change_confirmation_failed",
                credentials_id=current_user.public_id,
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
        payload: UpdateMePassword,
    ) -> None:
        credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            current_user.public_id,
            load_options=LoadOptionsSchema(load_sessions=True),
        )
        if credentials is None:
            raise CredentialsNotFoundError()

        if credentials.password_hash is None:
            raise IncorrectPasswordError()

        is_current_password_valid = await verify_password(
            payload.current_password, credentials.password_hash
        )

        if not is_current_password_valid:
            logger.warning(
                "password_change_denied",
                credentials_id=current_user.public_id,
                denial_reason="incorrect_current_password",
                method="self_service",
            )

            raise IncorrectPasswordError()

        if payload.current_password == payload.new_password:
            raise SamePasswordError()

        new_password_hash = await hash_password(payload.new_password)

        credentials.password_hash = new_password_hash

        session_ids = [s.id for s in credentials.sessions]

        await UserSessionRepository.invalidate_all_sessions(credentials.sessions)

        await session.commit()

        asyncio.create_task(
            send_email_safe(
                account.send_password_changed_notification(credentials.email),
                email_type=EmailType.PASSWORD_CHANGED,
            )
        )

        await delete_cache(
            redis,
            *[
                SessionCacheKey.access_token_version_key(session_id)
                for session_id in session_ids
            ],
        )

        logger.info(
            "password_changed",
            credentials_id=current_user.public_id,
            method="self_service",
        )
