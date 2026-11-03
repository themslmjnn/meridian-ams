from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.auth.models.login_lockout import UserLoginLockout


class UserLoginLockoutRepository:
    @staticmethod
    async def get_by_credentials_id(
        db_session: AsyncSession, credentials_id: int
    ) -> UserLoginLockout:
        query = (
            select(UserLoginLockout)
            .where(UserLoginLockout.credentials_id == credentials_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        result = await db_session.execute(query)

        return result.scalar_one()
