import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import CursorPage
from src.guardian_links.repository import GuardianLinkRepository
from src.guardian_links.schemas.director import GuardianLinkResponseDirector
from src.guardian_links.schemas.system_admin import SearchGuardianLink
from src.guardian_links.utils.exceptions import StudentNotFoundError
from src.guardian_links.utils.helpers import (
    build_guardian_link_response_director_from_row,
)
from src.users.repository.credentials import UserCredentialsRepository
from src.users.utils.enums import AccountType


class GuardianLinkServiceDirector:
    @staticmethod
    async def get_guardian_links(
        db_session: AsyncSession,
        *,
        filters: SearchGuardianLink | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[GuardianLinkResponseDirector]:
        page = await GuardianLinkRepository.get_links(
            db_session,
            filters=filters,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

        return CursorPage[GuardianLinkResponseDirector](
            items=[
                build_guardian_link_response_director_from_row(item)
                for item in page.items
            ],
            next_cursor=page.next_cursor,
            prev_cursor=page.prev_cursor,
            limit=page.limit,
        )

    @staticmethod
    async def get_links_by_student(
        db_session: AsyncSession, student_public_id: uuid.UUID
    ) -> list[GuardianLinkResponseDirector]:
        student = await UserCredentialsRepository.get_by_public_id(
            db_session, student_public_id
        )
        if student is None or student.account_type != AccountType.STUDENT:
            raise StudentNotFoundError()

        rows = await GuardianLinkRepository.get_links_by_student(db_session, student.id)

        return [build_guardian_link_response_director_from_row(row) for row in rows]
