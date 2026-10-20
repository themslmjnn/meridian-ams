from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.session import UserSession


class UserSessionRepository:
    @staticmethod
    async def get_by_id(
        db_session: AsyncSession,
        session_id: int,
        *,
        for_update: bool = False,
    ) -> UserSession | None:
        query = select(UserSession).where(UserSession.id == session_id)

        if for_update:
            query = query.with_for_update()

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_credentials_id(
        session: AsyncSession, credentials_id: int
    ) -> UserSession | None:
        query = (
            select(UserSession)
            .where(UserSession.credentials_id == credentials_id)
            .order_by(UserSession.id.desc())
            .limit(1)
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def invalidate_session(user_session: UserSession) -> None:
        user_session.access_token_version += 1
        user_session.refresh_token_hash = None
        user_session.refresh_token_expires_at = None

    @staticmethod
    async def invalidate_all_sessions(user_sessions: list[UserSession]) -> None:
        for user_session in user_sessions:
            await UserSessionRepository.invalidate_session(user_session)
