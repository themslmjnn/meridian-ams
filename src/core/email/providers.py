from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import httpx
import structlog

from src.core.config import get_settings

logger = structlog.get_logger(__name__)

_resend_client = httpx.AsyncClient(
    base_url="https://api.resend.com",
    timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
)


async def send_via_resend(
    subject: str,
    to_email: str,
    html_body: str,
) -> None:
    settings = get_settings()

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

    logger.info(
        "email_dispatched_resend",
        to_email=to_email,
        subject=subject,
    )


async def send_via_mailtrap(
    subject: str,
    to_email: str,
    html_body: str,
) -> None:
    settings = get_settings()

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
        password=settings.MAILTRAP_PASSWORD.get_secret_value(),
        start_tls=True,
    )

    logger.info(
        "email_dispatched_mailtrap",
        to_email=to_email,
        subject=subject,
    )


async def close_email_client() -> None:
    """
    Close the shared httpx client. Called in lifespan shutdown.
    Prevents ResourceWarning in tests and ensures clean shutdown.
    """

    await _resend_client.aclose()
