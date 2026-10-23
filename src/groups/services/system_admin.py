import uuid

import structlog
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import delete_cache
from src.groups.models import Group
from src.groups.repository import GroupRepository
from src.groups.schemas.system_admin import (
    CreateGroup,
    GroupResponseAdminDetailed,
    UpdateGroup,
)
from src.groups.utils.exceptions import (
    GroupNotFoundError,
    handle_group_name_per_academic_year,
)
from src.utils.cache_keys import GroupCacheKey
from src.utils.exceptions import raise_unhandled_integrity_error
from src.utils.helpers import update_object

logger = structlog.get_logger(__name__)


class GroupServiceAdmin:
    @staticmethod
    async def create_group(
        db_session: AsyncSession,
        actor_id: int,
        payload: CreateGroup,
    ) -> GroupResponseAdminDetailed:
        try:
            group = Group(**payload.model_dump())

            db_session.add(group)
            await db_session.commit()
            await db_session.refresh(group)

            logger.info(
                "group_created",
                group_id=group.id,
                created_by=actor_id,
            )

            response = GroupResponseAdminDetailed.model_validate(group)
            response.student_count = 0

            return response

        except IntegrityError as exc:
            await db_session.rollback()

            logger.warning(
                "group_creation_failed",
                error=str(exc.orig),
                requested_by=actor_id,
            )

            handle_group_name_per_academic_year(exc)
            raise_unhandled_integrity_error(exc)

    @staticmethod
    async def update_group(
        db_session: AsyncSession,
        redis: Redis,
        actor_id: int,
        public_id: uuid.UUID,
        payload: UpdateGroup,
    ) -> None:
        group = await GroupRepository.get_by_public_id(db_session, public_id)
        if group is None:
            raise GroupNotFoundError()

        try:
            update_object(group, payload)

            await db_session.commit()

            await delete_cache(
                redis,
                GroupCacheKey.group_detail_key_admin(group.id),
                GroupCacheKey.group_detail_key_staff(group.id),
            )

            logger.info(
                "group_updated",
                group_id=group.id,
                updated_by=actor_id,
            )

        except IntegrityError as exc:
            await db_session.rollback()

            logger.warning(
                "group_update_failed",
                error=str(exc.orig),
                group_public_id=public_id,
                requested_by=actor_id,
            )

            handle_group_name_per_academic_year(exc)
            raise_unhandled_integrity_error(exc)
