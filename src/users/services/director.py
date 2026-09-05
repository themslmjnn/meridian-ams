import uuid

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import get_cache, get_redis, set_cache
from src.core.pagination import CursorPage
from src.users.repository.user import (
    UserRepositoryBase,
)
from src.users.schemas.director import UserResponseDirectorDetailed
from src.users.schemas.system_admin import SearchUserBase
from src.users.utils.constants import TEACHER_ROLE
from src.users.utils.exceptions import UserNotFoundError
from src.utils.cache_keys import UserCacheKey

logger = structlog.get_logger(__name__)


class UserServiceDirector:
    @staticmethod
    async def get_staff(
        session: AsyncSession,
        *,
        filters: SearchUserBase | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[UserResponseDirectorDetailed]:
        page = await UserRepositoryBase.get_users(
            session,
            filters=filters,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            allowed_roles=TEACHER_ROLE,
        )

        return CursorPage[UserResponseDirectorDetailed](
            items=[
                UserResponseDirectorDetailed.model_validate(row) for row in page.items
            ],
            next_cursor=page.next_cursor,
            prev_cursor=page.prev_cursor,
            limit=page.limit,
        )

    @staticmethod
    async def get_staff_by_public_id(
        request: Request, session: AsyncSession, public_id: uuid.UUID
    ) -> UserResponseDirectorDetailed:
        cache_key = UserCacheKey.user_detail_key_staff(public_id)

        redis = get_redis(request)
        cached = await get_cache(redis, cache_key)

        if cached is not None:
            return UserResponseDirectorDetailed.model_validate(cached)

        staff = await UserRepositoryBase.get_user_by_public_id(
            session, public_id, allowed_roles=TEACHER_ROLE
        )
        if staff is None:
            raise UserNotFoundError()

        response = UserResponseDirectorDetailed.model_validate(staff)

        await set_cache(redis, cache_key, response.model_dump(mode="json"), 900)

        return response
