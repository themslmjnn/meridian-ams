from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.auth.models.session import UserSession


class UserSessionRepository:
    @staticmethod
    async def get_by_id(
        db_session: AsyncSession, session_id: int
    ) -> UserSession | None:
        query = select(UserSession).where(UserSession.id == session_id)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()
