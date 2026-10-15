from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.activation import UserActivation
from src.users.models.identity import UserIdentity


class UserActivationRepository:
    @staticmethod
    async def get_by_credentials_id(
        session: AsyncSession, credentials_id: int
    ) -> UserIdentity | None:
        query = select(UserActivation).where(
            UserActivation.credentials_id == credentials_id
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()
