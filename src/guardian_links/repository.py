from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.guardian_links.models import StudentGuardianLink


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
