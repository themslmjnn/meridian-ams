import uuid
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import delete_cache, get_cache, set_cache
from src.groups.models import Group
from src.groups.repository import GroupRepository
from src.groups.schemas.system_admin import (
    CreateGroup,
    GroupResponseAdminDetailed,
    GroupResponseBase,
    SearchGroupAdmin,
    UpdateGroup,
)
from src.groups.utils.enums import GroupSortField
from src.groups.utils.exceptions import (
    GroupAlreadyArchivedError,
    GroupNotArchivedError,
    GroupNotFoundError,
    handle_group_name_per_academic_year,
)
from src.utils.cache_keys import GroupCacheKey
from src.utils.enums import OrderBy
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

    @staticmethod
    async def archive_group(
        db_session: AsyncSession,
        redis: Redis,
        actor_id: int,
        public_id: uuid.UUID,
    ) -> None:
        group = await GroupRepository.get_by_public_id(db_session, public_id)
        if group is None:
            raise GroupNotFoundError()

        if group.is_archived:
            raise GroupAlreadyArchivedError()

        student_count = await GroupRepository.count_active_students(
            db_session, group.id
        )

        group.is_archived = True
        group.archived_at = datetime.now(UTC)

        await db_session.commit()

        await delete_cache(
            redis,
            GroupCacheKey.group_detail_key_admin(group.id),
            GroupCacheKey.group_detail_key_staff(group.id),
        )

        logger.info(
            "group_archived",
            group_public_id=public_id,
            archived_by=actor_id,
        )

        return student_count

    @staticmethod
    async def restore_group(
        db_session: AsyncSession,
        redis: Redis,
        actor_id: int,
        public_id: uuid.UUID,
    ) -> None:
        group = await GroupRepository.get_by_public_id(db_session, public_id)
        if group is None:
            raise GroupNotFoundError()

        if not group.is_archived:
            raise GroupNotArchivedError()

        group.is_archived = False
        group.archived_at = None

        await db_session.commit()

        await delete_cache(
            redis,
            GroupCacheKey.group_detail_key_admin(group.id),
            GroupCacheKey.group_detail_key_staff(group.id),
        )

        logger.info(
            "group_restored",
            group_public_id=public_id,
            restored_by=actor_id,
        )

    @staticmethod
    async def get_groups(
        db_session: AsyncSession,
        filters: SearchGroupAdmin,
        sort_by: GroupSortField,
        order: OrderBy,
    ) -> list[GroupResponseBase]:
        groups = await GroupRepository.get_groups(db_session, filters, sort_by, order)

        return [GroupResponseBase.model_validate(group) for group in groups]

    @staticmethod
    async def get_group_by_public_id(
        db_session: AsyncSession,
        redis: Redis,
        public_id: uuid.UUID,
    ) -> GroupResponseAdminDetailed:
        cache_key = GroupCacheKey.group_detail_key_admin(public_id)

        cached_data = await get_cache(redis, cache_key)
        if cached_data is not None:
            return GroupResponseAdminDetailed.model_validate(cached_data)

        group = await GroupRepository.get_by_public_id(db_session, public_id)
        if group is None:
            raise GroupNotFoundError()

        student_count = await GroupRepository.count_active_students(
            db_session, group.id
        )

        response = GroupResponseAdminDetailed.model_validate(group).model_copy(
            update={"student_count": student_count}
        )

        await set_cache(redis, cache_key, response.model_dump(mode="json"), 900)

        return response
