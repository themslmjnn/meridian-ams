from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.guardian_links.models import StudentGuardianLink
from src.guardian_links.utils.enums import GuardianType


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
