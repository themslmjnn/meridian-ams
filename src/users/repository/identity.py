from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.identity import UserIdentity


class UserIdentityRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, identity_id: int) -> UserIdentity | None:
        query = select(UserIdentity).where(UserIdentity.id == identity_id)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def count_identities(session: AsyncSession, identity_id: int) -> int:
        """
        Count how many credentials rows reference this identity.
        Used by the deletion worker to decide whether to also delete
        the identity after deleting the guardian's credentials.
        """

        query = (
            select(func.count())
            .select_from(UserIdentity)
            .where(UserIdentity.id == identity_id)
        )

        result = await session.execute(query)

        return result.scalar_one()
