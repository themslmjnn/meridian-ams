import uuid

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import CursorPage
from src.guardian_links.models import StudentGuardianLink
from src.guardian_links.repository import GuardianLinkRepository
from src.guardian_links.schemas.system_admin import (
    CreateGuardianLink,
    GuardianLinkResponse,
    SearchGuardianLink,
)
from src.guardian_links.utils.exceptions import (
    GuardianAlreadyLinkedError,
    GuardianNotFoundError,
    GuardianTypeTakenError,
    InvalidGuardianAccountError,
    InvalidStudentAccountError,
    InvalidStudentStatusError,
    StudentNotFoundError,
    handle_duplicate_link_error,
    handle_guardian_type_error,
)
from src.guardian_links.utils.helpers import (
    build_guardian_link_response,
    build_guardian_link_response_from_row,
)
from src.users.repository.credentials import UserCredentialsRepository
from src.users.utils.enums import AccountType, UserStatus
from src.users.utils.schemas import LoadOptionsSchema
from src.utils.exceptions import raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)


class GuardianLinkService:
    @staticmethod
    async def create_guardian_link(
        db_session: AsyncSession,
        actor_id: int,
        payload: CreateGuardianLink,
    ) -> GuardianLinkResponse:
        guardian = await UserCredentialsRepository.get_by_public_id(
            db_session,
            payload.guardian_public_id,
            load_options=LoadOptionsSchema(load_identity=True),
        )
        if guardian is None:
            raise GuardianNotFoundError()

        if guardian.account_type != AccountType.PERSONAL:
            raise InvalidGuardianAccountError(
                "Only personal accounts can be linked as guardians"
            )

        if guardian.status != UserStatus.ACTIVE:
            raise InvalidGuardianAccountError(
                "Guardian account must be active to be linked"
            )

        student = await UserCredentialsRepository.get_by_public_id(
            db_session,
            payload.student_public_id,
            load_options=LoadOptionsSchema(load_identity=True),
        )
        if student is None:
            raise StudentNotFoundError()

        if student.account_type != AccountType.STUDENT:
            raise InvalidStudentAccountError()

        if student.status not in (
            UserStatus.ACTIVE,
            UserStatus.PENDING_ACTIVATION,
        ):
            raise InvalidStudentStatusError()

        existing_links = await GuardianLinkRepository.get_by_student_credentials_id(
            db_session, student.id
        )
        if any(link.guardian_credentials_id == guardian.id for link in existing_links):
            raise GuardianAlreadyLinkedError()

        if any(link.guardian_type == payload.guardian_type for link in existing_links):
            raise GuardianTypeTakenError()

        try:
            new_link = StudentGuardianLink(
                student_credentials_id=student.id,
                guardian_credentials_id=guardian.id,
                guardian_type=payload.guardian_type,
            )

            db_session.add(new_link)
            await db_session.flush()

        except IntegrityError as exc:
            await db_session.rollback()

            logger.error(
                "guardian_link_creation_failed",
                failure_reason="integrity_error",
                error=str(exc.orig),
                actor_id=actor_id,
            )

            handle_duplicate_link_error(exc)
            handle_guardian_type_error(exc)
            raise_unhandled_integrity_error(exc)

        logger.info(
            "guardian_linked",
            actor_id=actor_id,
            guardian_public_id=payload.guardian_public_id,
            student_public_id=payload.student_public_id,
            guardian_type=payload.guardian_type,
        )

        return build_guardian_link_response(guardian, student, payload.guardian_type)

    @staticmethod
    async def delete_guardian_link(
        db_session: AsyncSession,
        actor_id: int,
        student_public_id: uuid.UUID,
        guardian_public_id: uuid.UUID,
    ) -> None:
        student = await UserCredentialsRepository.get_by_public_id(
            db_session, student_public_id
        )
        if student is None:
            raise StudentNotFoundError()

        guardian = await UserCredentialsRepository.get_by_public_id(
            db_session, guardian_public_id
        )
        if guardian is None:
            raise GuardianNotFoundError()

        deleted_type = await GuardianLinkRepository.delete_by_pair(
            db_session, student.id, guardian.id
        )

        if deleted_type is None:
            return

        await db_session.commit()

        logger.info(
            "guardian_unlinked",
            actor_id=actor_id,
            guardian_public_id=guardian_public_id,
            student_public_id=student_public_id,
            guardian_type=deleted_type,
        )

    @staticmethod
    async def get_guardian_links(
        db_session: AsyncSession,
        *,
        filters: SearchGuardianLink | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[GuardianLinkResponse]:
        page = await GuardianLinkRepository.get_links(
            db_session,
            filters=filters,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

        return CursorPage[GuardianLinkResponse](
            items=[build_guardian_link_response_from_row(item) for item in page.items],
            next_cursor=page.next_cursor,
            prev_cursor=page.prev_cursor,
            limit=page.limit,
        )

    @staticmethod
    async def get_links_by_student(
        db_session: AsyncSession, student_public_id: uuid.UUID
    ) -> list[GuardianLinkResponse]:
        student = await UserCredentialsRepository.get_by_public_id(
            db_session, student_public_id
        )
        if student is None or student.account_type != AccountType.STUDENT:
            raise StudentNotFoundError()

        rows = await GuardianLinkRepository.get_links_by_student(db_session, student.id)

        return [build_guardian_link_response_from_row(row) for row in rows]

    @staticmethod
    async def get_links_by_guardian(
        db_session: AsyncSession, guardian_public_id: uuid.UUID
    ) -> list[GuardianLinkResponse]:
        guardian = await UserCredentialsRepository.get_by_public_id(
            db_session, guardian_public_id
        )
        if guardian is None or guardian.account_type != AccountType.PERSONAL:
            raise GuardianNotFoundError()

        rows = await GuardianLinkRepository.get_links_by_guardian(
            db_session, guardian.id
        )

        return [build_guardian_link_response_from_row(row) for row in rows]
