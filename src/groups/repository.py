import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.groups.models import Group, StudentGroupAssignment
from src.groups.schemas.system_admin import SearchGroupAdmin, SearchGroupBase
from src.groups.utils.enums import GroupSortField
from src.utils.enums import OrderBy


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

    @staticmethod
    def _apply_filters(
        query: Select, filters: SearchGroupBase | SearchGroupAdmin
    ) -> Select:
        if filters is not None:
            if filters.name:
                query = query.where(Group.name.ilike(f"%{filters.name}%"))

            if filters.academic_year:
                query = query.where(Group.academic_year == filters.academic_year)

            if filters.grade_level:
                query = query.where(Group.grade_level == filters.grade_level)

            include_archived = (
                isinstance(filters, SearchGroupAdmin) and filters.include_archived
            )

            if include_archived:
                query = query.where(Group.is_archived.is_(True))

        return query

    @staticmethod
    def _apply_sorting(
        query: Select, sort_by: GroupSortField, order: OrderBy
    ) -> Select:
        column = getattr(Group, sort_by.value)

        if order == OrderBy.DESC:
            return query.order_by(column.desc(), Group.id.desc())

        return query.order_by(column.asc(), Group.id.asc())

    @staticmethod
    async def get_groups(
        db_session: AsyncSession,
        filters: SearchGroupBase | SearchGroupAdmin,
        sort_by: GroupSortField,
        order: OrderBy,
    ) -> list[Group]:
        query = GroupRepository._apply_filters(select(Group), filters)
        query = GroupRepository._apply_sorting(query, sort_by, order)

        result = await db_session.execute(query)

        return result.scalars().all()
