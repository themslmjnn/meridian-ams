from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import httpx
import structlog

from src.core.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_resend_client = httpx.AsyncClient(
    base_url="https://api.resend.com",
    timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
)


async def _send_via_resend(
    subject: str,
    to_email: str,
    html_body: str,
) -> None:
    response = await _resend_client.post(
        "/emails",
        json={
            "from": f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        },
        headers={
            "Authorization": f"Bearer {settings.EMAIL_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Resend API error {response.status_code}: {response.text[:400]}"
        )

    logger.info("email_dispatched_resend", to_email=to_email, subject=subject)


async def _send_via_mailtrap(
    subject: str,
    to_email: str,
    html_body: str,
) -> None:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
    message["To"] = to_email
    message.attach(MIMEText(html_body, "html"))

    await aiosmtplib.send(
        message,
        hostname=settings.MAILTRAP_HOST,
        port=settings.MAILTRAP_PORT,
        username=settings.MAILTRAP_USERNAME,
        password=settings.MAILTRAP_PASSWORD,
        start_tls=True,
    )

    logger.info("email_dispatched_mailtrap", to_email=to_email, subject=subject)


async def send_email(subject: str, to_email: str, html_body: str) -> None:
    """
    Send an email via the appropriate provider for the current environment.
    Raises on delivery failure — caller (worker) handles retry logic.
    """
    if settings.ENVIRONMENT == "development":
        await _send_via_mailtrap(subject, to_email, html_body)
    else:
        await _send_via_resend(subject, to_email, html_body)


async def send_email_safe(subject: str, to_email: str, html_body: str) -> None:
    """
    Fire-and-forget send. Swallows all exceptions and logs them as warnings.
    Use for informational emails where delivery failure is acceptable
    and no retry or DB record is needed.

    Never use this inside the worker — the worker needs exceptions to surface
    so it can record failures and drive retry logic.
    """
    try:
        await send_email(subject, to_email, html_body)

    except Exception as exc:
        logger.warning(
            "email_safe_send_failed",
            to_email=to_email,
            subject=subject,
            error_type=type(exc).__name__,
            error=str(exc),
        )


async def close_email_client() -> None:
    """
    Close the shared httpx client. Called in lifespan shutdown.
    Prevents ResourceWarning in tests and ensures clean shutdown.
    """
    await _resend_client.aclose()
