import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.groups.models import Group, StudentGroupAssignment


class GroupRepository:
    @staticmethod
    async def get_by_public_id(
        db_session: AsyncSession, public_id: uuid.UUID
    ) -> Group | None:
        query = select(Group).where(Group.public_id == public_id)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def count_active_students(db_session: AsyncSession, group_id: int) -> int:
        query = select(func.count()).where(
            StudentGroupAssignment.group_id == group_id,
            StudentGroupAssignment.unassigned_at.is_(None),
        )

        result = await db_session.execute(query)

        return result.scalar_one()
