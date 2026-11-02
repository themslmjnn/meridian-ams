import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from meridian_ams.core.config import get_settings
from meridian_ams.core.email.service import send_email
from meridian_ams.database.connection import build_session_factory
from meridian_ams.emails.enums import EmailStatus
from meridian_ams.emails.models import Email
from meridian_ams.emails.repository import EmailRepository

logger = structlog.get_logger(__name__)

settings = get_settings()


async def _process_email(db_session: AsyncSession, record: Email) -> None:
    """
    Attempt to send a single email record.
    Updates the record's status and commits in both success and failure paths.
    Never raises — errors are recorded on the row and logged.
    """

    structlog.contextvars.bind_contextvars(
        email_id=record.id,
        email_type=record.email_type,
        recipient_email=record.recipient_email,
    )

    try:
        await send_email(
            subject=record.subject,
            to_email=record.recipient_email,
            html_body=record.html_body,
        )

        await EmailRepository.mark_sent(record)
        await db_session.commit()

        logger.info("email_worker_sent")

    except asyncio.CancelledError:
        await db_session.rollback()

        raise

    except Exception as exc:
        await EmailRepository.mark_failed_attempt(record, repr(exc))

        await db_session.commit()

        if record.status == EmailStatus.FAILED:
            logger.error(
                "email_worker_exhausted_retries",
                retry_count=record.retry_count,
                error_type=type(exc).__name__,
                error=repr(exc),
            )
        else:
            logger.warning(
                "email_worker_attempt_failed",
                retry_count=record.retry_count,
                error_type=type(exc).__name__,
                error=repr(exc),
            )

    finally:
        structlog.contextvars.clear_contextvars()


async def _run_sweep(engine: AsyncEngine) -> None:
    """
    One full sweep of the pending queue.
    Opens a fresh session per batch and continues until the queue is drained.
    """

    batch_size = settings.EMAIL_WORKER_BATCH_SIZE

    while True:
        async with build_session_factory(engine) as session:
            batch = await EmailRepository.get_pending_batch(session, limit=batch_size)

            if not batch:
                break

            logger.info("email_worker_sweep_batch", batch_size=len(batch))

            for record in batch:
                await _process_email(session, record)

            if len(batch) < batch_size:
                break


async def run_email_worker(engine: AsyncEngine) -> None:
    logger.info(
        "email_worker_started",
        poll_interval=settings.EMAIL_WORKER_INTERVAL,
        batch_size=settings.EMAIL_WORKER_BATCH_SIZE,
    )

    while True:
        try:
            await _run_sweep(engine)

        except asyncio.CancelledError:
            logger.info("email_worker_stopping")

            raise

        except Exception as exc:
            logger.error(
                "email_worker_sweep_failed",
                error_type=type(exc).__name__,
                error=repr(exc),
            )

        await asyncio.sleep(settings.EMAIL_WORKER_INTERVAL)
