import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.groups.models import Group
from src.groups.schemas.system_admin import CreateGroup, GroupResponseAdminDetailed
from src.groups.utils.exceptions import handle_group_name_per_academic_year
from src.utils.exceptions import raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)


class GroupServiceAdmin:
    @staticmethod
    async def create_group(
        db_session: AsyncSession,
        actor_id: int,
        payload: CreateGroup,
    ) -> GroupResponseAdminDetailed:
        try:
            group = Group(**payload.model_dump())

            db_session.add(group)
            await db_session.commit()
            await db_session.refresh(group)

            logger.info(
                "group_created",
                group_id=group.id,
                created_by=actor_id,
            )

        except IntegrityError as exc:
            await db_session.rollback()

            logger.warning(
                "group_creation_failed",
                error=str(exc.orig),
                requested_by=actor_id,
            )

            handle_group_name_per_academic_year(exc)
            raise_unhandled_integrity_error(exc)
