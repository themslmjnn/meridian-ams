from sqlalchemy import func, select
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

    @staticmethod
    async def get_by_device_id(
        db_session: AsyncSession,
        credentials_id: int,
        device_id: str,
    ) -> UserSession | None:
        query = select(UserSession).where(
            UserSession.credentials_id == credentials_id,
            UserSession.device_id == device_id,
        )

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_session_count(db_session: AsyncSession, credentials_id: int) -> int:
        query = (
            select(func.count())
            .select_from(UserSession)
            .where(
                UserSession.credentials_id == credentials_id,
            )
        )

        result = await db_session.execute(query)

        return result.scalar_one()

    @staticmethod
    async def get_session_ids(
        db_session: AsyncSession, credentials_id: int
    ) -> list[int]:
        query = select(UserSession.id).where(
            UserSession.credentials_id == credentials_id
        )

        result = await db_session.execute(query)

        return result.scalars().all()

    @staticmethod
    async def evict_oldest_session(
        db_session: AsyncSession, credentials_id: int
    ) -> int | None:
        """Delete the user's oldest session and return its ID, or None if none exist."""

        query = (
            select(UserSession)
            .where(UserSession.credentials_id == credentials_id)
            .order_by(
                UserSession.refresh_token_hash.is_(None).desc(),
                UserSession.last_active_at.asc().nulls_first(),
                UserSession.created_at.asc(),
            )
            .limit(1)
        )

        result = await db_session.execute(query)

        oldest = result.scalar_one_or_none()

        if oldest is None:
            return None

        evicted_id = oldest.id

        await db_session.delete(oldest)
        await db_session.flush()

        return evicted_id
