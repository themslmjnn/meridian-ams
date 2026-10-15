from collections.abc import Awaitable
from typing import Any

import structlog

from src.core.config import get_settings
from src.core.email.providers import send_via_mailtrap, send_via_resend

logger = structlog.get_logger(__name__)

settings = get_settings()


async def send_email(subject: str, to_email: str, html_body: str) -> None:
    """
    Send an email via the appropriate provider for the current environment.
    Raises on delivery failure — caller (worker) handles retry logic.
    """

    if settings.ENVIRONMENT == "development":
        await send_via_mailtrap(subject, to_email, html_body)
    else:
        await send_via_resend(subject, to_email, html_body)


async def send_email_safe(email_operation: Awaitable[Any], **log_context: Any) -> None:
    """
    Fire-and-forget send. Swallows all exceptions and logs them as warnings.
    Use for informational emails where delivery failure is acceptable
    and no retry or DB record is needed.

    Never use this inside the worker — the worker needs exceptions to surface
    so it can record failures and drive retry logic.
    """

    try:
        await email_operation

    except Exception as exc:
        logger.error(
            "background_email_task_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            **log_context,
        )
