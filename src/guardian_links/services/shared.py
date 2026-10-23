from sqlalchemy.ext.asyncio import AsyncSession

from src.guardian_links.repository import GuardianLinkRepository
from src.guardian_links.schemas.shared import (
    MyGuardianLinkResponse,
    MyStudentLinkResponse,
)
from src.guardian_links.utils.helpers import (
    build_my_guardian_link_from_row,
    build_my_student_link_from_row,
)


class GuardianLinkServiceShared:
    @staticmethod
    async def get_my_students(
        db_session: AsyncSession, guardian_credentials_id: int
    ) -> list[MyStudentLinkResponse]:
        rows = await GuardianLinkRepository.get_links_by_guardian(
            db_session, guardian_credentials_id
        )

        return [build_my_student_link_from_row(row) for row in rows]

    @staticmethod
    async def get_my_guardians(
        db_session: AsyncSession, student_credentials_id: int
    ) -> list[MyGuardianLinkResponse]:
        rows = await GuardianLinkRepository.get_links_by_student(
            db_session, student_credentials_id
        )

        return [build_my_guardian_link_from_row(row) for row in rows]
