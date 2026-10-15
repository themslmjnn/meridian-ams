from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.password_reset import UserPasswordReset


class UserPasswordResetRepository:
    @staticmethod
    async def get_by_credentials_id(
        session: AsyncSession, credentials_id: int
    ) -> UserPasswordReset | None:
        query = select(UserPasswordReset).where(
            UserPasswordReset.credentials_id == credentials_id
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()