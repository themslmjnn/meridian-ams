import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import delete_cache, get_cache, get_redis, set_cache
from src.core.config import get_settings
from src.core.dependencies import CurrentUser
from src.core.security import generate_email_change_code
from src.emails.utils.enums import EmailType
from src.users.repository.user import UserCredentialsRepository, UserRepositoryBase
from src.users.schemas.shared import UpdateUserCredentials, UserResponseSelf
from src.users.utils.constants import STUDENT_ROLE
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    DuplicateEmailChangeRequestError,
    UserNotFoundError,
    handle_username_integrity_error,
)
from src.users.utils.schemas import LoadOptionsSchema
from src.utils import email as emails
from src.utils.cache_keys import SessionCacheKey, UserCacheKey
from src.utils.exceptions import NoChangesDetectedError, raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)


class UserServiceSelf:
    @staticmethod
    async def get_my_profile(
        request: Request, session: AsyncSession, current_user: CurrentUser
    ) -> UserResponseSelf:
        cache_key = UserCacheKey.user_detail_key_self(current_user.id)
        cached = await get_cache(get_redis(request), cache_key)

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

        await set_cache(
            get_redis(request), cache_key, response.model_dump(mode="json"), 900
        )

        return response

    @staticmethod
    async def update_me_credentials(
        request: Request,
        session: AsyncSession,
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
                get_redis(request),
                UserCacheKey.user_detail_key_admin(target_user.id),
                UserCacheKey.user_detail_key_staff(target_user.id),
                UserCacheKey.user_detail_key_self(target_user.id),
            )

            if username_changing:
                await delete_cache(
                    get_redis(request),
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
