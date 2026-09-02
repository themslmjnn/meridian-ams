from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.session import UserSession


class AuthRepository:
    @staticmethod
    async def get_session_by_device_id(
        session: AsyncSession,
        credentials_id: int,
        device_id: str,
    ) -> UserSession | None:
        query = select(UserSession).where(
            UserSession.credentials_id == credentials_id,
            UserSession.device_id == device_id,
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_session_count(
        session: AsyncSession,
        credentials_id: int,
    ) -> int:
        query = (
            select(func.count())
            .select_from(UserSession)
            .where(
                UserSession.credentials_id == credentials_id,
            )
        )

        result = await session.execute(query)

        return result.scalar_one()

    @staticmethod
    async def evict_oldest_session(
        session: AsyncSession,
        credentials_id: int,
    ) -> None:
        # Find the session with the oldest last_active_at.
        # NULL last_active_at means never used — evict those first.
        query = (
            select(UserSession)
            .where(UserSession.credentials_id == credentials_id)
            .order_by(
                UserSession.last_active_at.asc().nulls_first(),
                UserSession.created_at.asc(),
            )
            .limit(1)
        )

        result = await session.execute(query)

        oldest = result.scalar_one_or_none()

        if oldest is not None:
            await session.delete(oldest)
            await session.flush()

    @staticmethod
    async def delete_session(
        session: AsyncSession,
        user_session: UserSession,
    ) -> None:
        await session.delete(user_session)
        await session.flush()
