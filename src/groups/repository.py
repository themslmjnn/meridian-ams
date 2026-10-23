import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.groups.models import Group


class GroupRepository:
    @staticmethod
    async def get_by_public_id(
        db_session: AsyncSession, public_id: uuid.UUID
    ) -> Group | None:
        query = select(Group).where(Group.public_id == public_id)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()
