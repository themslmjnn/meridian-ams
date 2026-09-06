from __future__ import annotations

import asyncio

import structlog

from src.core.config import get_settings
from src.database.connection import session_factory
from src.users.repository.user import UserCredentialsRepository, UserIdentityRepository

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 50


async def _run_deletion_sweep() -> None:
    """
    Fetch one batch of due credentials IDs and process each within a single
    database connection, using savepoints for per-row error isolation.

    Savepoint behaviour:
    - A failure on one row rolls back only to that row's savepoint.
    - The session remains clean for the next row.
    - All successful deletions commit together at the end.

    Re-processing safety:
    - If the app crashes after processing rows but before the final commit,
      those rows are re-processed on the next sweep.
    - get_credentials_if_due re-verifies conditions before acting, so
      re-processing an already-deleted row safely returns None and skips.
    """

    deleted_ids: list[int] = []
    skipped_ids: list[int] = []
    failed_ids: list[int] = []

    async with session_factory() as session:
        try:
            batch = await UserCredentialsRepository.get_due_for_deletion(
                session, limit=_BATCH_SIZE
            )

        except Exception as exc:
            logger.error(
                "deletion_sweep_batch_fetch_failed",
                error=str(exc),
            )

            return

        if not batch:
            return

        for credentials_id in batch:
            try:
                async with session.begin_nested():
                    credentials = (
                        await UserCredentialsRepository.get_credentials_if_due(
                            session, credentials_id
                        )
                    )

                    if credentials is None:
                        # Cancelled or already deleted between batch fetch and now.
                        skipped_ids.append(credentials_id)

                        continue

                    identity_id = credentials.identity_id
                    scheduled_for = credentials.deletion_scheduled_for.isoformat()

                    await session.delete(credentials)
                    await session.flush()

                    # Delete the identity only if no other credentials row
                    # references it. A staff member who also had a personal
                    # account shares one identity with their work account —
                    # deleting the identity here would destroy the work account.
                    remaining = await UserIdentityRepository.count_credentials(
                        session, identity_id
                    )

                    identity_deleted = False
                    if remaining == 0:
                        identity = await UserIdentityRepository.get_by_id(
                            session, identity_id
                        )
                        if identity is not None:
                            await session.delete(identity)

                            identity_deleted = True

                # Savepoint released — this deletion is committed to the session.
                deleted_ids.append(credentials_id)

                logger.info(
                    "guardian_hard_deleted",
                    credentials_id=credentials_id,
                    identity_id=identity_id,
                    identity_deleted=identity_deleted,
                    scheduled_for=scheduled_for,
                )

            except Exception as exc:
                # Savepoint rolled back — only this row is affected.
                # Session is still clean for the next row.
                failed_ids.append(credentials_id)

                logger.error(
                    "guardian_deletion_failed",
                    credentials_id=credentials_id,
                    error=str(exc),
                )

        await session.commit()

    logger.info(
        "deletion_sweep_completed",
        deleted=len(deleted_ids),
        deleted_ids=deleted_ids,
        skipped=len(skipped_ids),
        skipped_ids=skipped_ids,
        failed=len(failed_ids),
        failed_ids=failed_ids,
    )


async def run_deletion_worker() -> None:
    """
    Long-running background task. Started in app lifespan, cancelled on shutdown.

    Sweeps immediately on startup so the first run does not wait a full interval.
    CancelledError propagates cleanly to allow lifespan shutdown to complete.
    """

    logger.info("deletion_worker_started")

    while True:
        try:
            await _run_deletion_sweep()

        except asyncio.CancelledError:
            logger.info("deletion_worker_stopping")

            raise

        except Exception as exc:
            logger.error(
                "deletion_sweep_failed",
                error=str(exc),
            )

        try:
            await asyncio.sleep(get_settings().DELETION_WORKER_INTERVAL)

        except asyncio.CancelledError:
            logger.info("deletion_worker_stopping")

            raise
