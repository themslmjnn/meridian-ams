from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.users.models.identity import UserIdentity


class UserIdentityRepository:
    @staticmethod
    async def get_by_id(
        db_session: AsyncSession, identity_id: int
    ) -> UserIdentity | None:
        query = select(UserIdentity).where(UserIdentity.id == identity_id)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()
