from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.activation import UserActivation


class UserActivationRepository:
    @staticmethod
    async def get_by_credentials_id(
        db_session: AsyncSession, credentials_id: int
    ) -> UserActivation | None:
        query = select(UserActivation).where(
            UserActivation.credentials_id == credentials_id
        )

        result = await db_session.execute(query)

        return result.scalar_one_or_none()
