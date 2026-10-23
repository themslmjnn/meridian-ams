from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.pagination import CursorPage, paginate_mapped
from src.guardian_links.models import StudentGuardianLink
from src.guardian_links.schemas.system_admin import SearchGuardianLink
from src.guardian_links.utils.enums import GuardianType
from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity

_guardian = aliased(UserCredentials, name="guardian_creds")
_student = aliased(UserCredentials, name="student_creds")
_guardian_identity = aliased(UserIdentity, name="guardian_identity")
_student_identity = aliased(UserIdentity, name="student_identity")


class GuardianLinkRepository:
    @staticmethod
    async def get_by_student_credentials_id(
        db_session: AsyncSession, student_credentials_id: int
    ) -> Sequence[StudentGuardianLink]:
        query = select(StudentGuardianLink).where(
            StudentGuardianLink.student_credentials_id == student_credentials_id
        )

        result = await db_session.execute(query)

        return result.scalars().all()

    @staticmethod
    async def delete_by_pair(
        db_session: AsyncSession,
        student_credentials_id: int,
        guardian_credentials_id: int,
    ) -> GuardianType | None:
        """Delete the link and return its type, or None if no link existed."""

        query = (
            delete(StudentGuardianLink)
            .where(
                StudentGuardianLink.student_credentials_id == student_credentials_id,
                StudentGuardianLink.guardian_credentials_id == guardian_credentials_id,
            )
            .returning(StudentGuardianLink.guardian_type)
        )

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    def _base_query() -> Select:
        return (
            select(
                _guardian.public_id.label("guardian_public_id"),
                _guardian_identity.firstname.label("guardian_firstname"),
                _guardian_identity.lastname.label("guardian_lastname"),
                _guardian_identity.middlename.label("guardian_middlename"),
                _student.public_id.label("student_public_id"),
                _student_identity.firstname.label("student_firstname"),
                _student_identity.lastname.label("student_lastname"),
                _student_identity.middlename.label("student_middlename"),
                StudentGuardianLink.guardian_type,
            )
            .select_from(StudentGuardianLink)
            .join(
                _guardian, _guardian.id == StudentGuardianLink.guardian_credentials_id
            )
            .join(_guardian_identity, _guardian_identity.id == _guardian.identity_id)
            .join(_student, _student.id == StudentGuardianLink.student_credentials_id)
            .join(_student_identity, _student_identity.id == _student.identity_id)
        )

    @staticmethod
    def _apply_filters(query: Select, filters: SearchGuardianLink | None) -> Select:
        if filters is not None:
            if filters.guardian_type:
                query = query.where(
                    StudentGuardianLink.guardian_type == filters.guardian_type
                )
            if filters.guardian_firstname:
                query = query.where(
                    _guardian_identity.firstname.ilike(
                        f"%{filters.guardian_firstname}%"
                    )
                )
            if filters.guardian_lastname:
                query = query.where(
                    _guardian_identity.lastname.ilike(f"%{filters.guardian_lastname}%")
                )
            if filters.student_firstname:
                query = query.where(
                    _student_identity.firstname.ilike(f"%{filters.student_firstname}%")
                )
            if filters.student_lastname:
                query = query.where(
                    _student_identity.lastname.ilike(f"%{filters.student_lastname}%")
                )

        return query

    @staticmethod
    async def get_links(
        db_session: AsyncSession,
        *,
        filters: SearchGuardianLink | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[dict[str, Any]]:
        query = GuardianLinkRepository._apply_filters(
            GuardianLinkRepository._base_query(), filters
        )

        return await paginate_mapped(
            db_session,
            query,
            created_at_column=StudentGuardianLink.created_at,
            id_column=StudentGuardianLink.id,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )
