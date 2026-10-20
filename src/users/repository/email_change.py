from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.email_change import UserEmailChange


class UserEmailChangeRepository:
    @staticmethod
    async def get_by_credentials_id(
        db_session: AsyncSession, credentials_id: int
    ) -> UserEmailChange | None:
        query = select(UserEmailChange).where(
            UserEmailChange.credentials_id == credentials_id
        )

        result = await db_session.execute(query)

        return result.scalar_one_or_none()
