import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import get_cache, get_redis, set_cache
from src.core.dependencies import CurrentUser
from src.users.repository.user import UserRepositoryBase
from src.users.schemas.shared import UserResponseSelf
from src.users.utils.constants import STUDENT_ROLE
from src.users.utils.exceptions import UserNotFoundError
from src.utils.cache_keys import UserCacheKey

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
