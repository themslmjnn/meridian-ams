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


def build_activation_email(
    activation_token: str,
    username: str,
) -> tuple[str, str]:
    activation_link = f"{settings.APP_URL}/auth/activation?token={activation_token}"

    subject = "Activate your Meridian account"

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>

    <body
        style="
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
            background-color: #f5f6f8;
            color: #374151;
        "
    >
        <div style="padding: 40px 20px;">
            <div
                style="
                    max-width: 560px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 10px;
                    padding: 40px;
                    box-sizing: border-box;
                "
            >
                <h1
                    style="
                        margin: 0 0 30px;
                        font-size: 22px;
                        color: #1f2937;
                    "
                >
                    LFGS | Meridian
                </h1>

                <h2
                    style="
                        margin: 0 0 20px;
                        font-size: 20px;
                        color: #1f2937;
                    "
                >
                    Activate your account
                </h2>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    Hello,
                </p>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    An account has been created for you in
                    <strong>LFGS | Meridian</strong>.
                </p>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    Your username is:
                </p>

                <div
                    style="
                        display: inline-block;
                        background-color: #f3f4f6;
                        padding: 10px 14px;
                        border-radius: 6px;
                        font-family: monospace;
                        font-size: 15px;
                        margin-bottom: 24px;
                    "
                >
                    {username}
                </div>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    Click the button below to activate your account and create
                    your password.
                </p>

                <div style="text-align: center; margin: 32px 0;">
                    <a
                        href="{activation_link}"
                        style="
                            display: inline-block;
                            background-color: #2563eb;
                            color: #ffffff;
                            padding: 13px 26px;
                            border-radius: 6px;
                            text-decoration: none;
                            font-weight: bold;
                        "
                    >
                        Activate Account
                    </a>
                </div>

                <p
                    style="
                        font-size: 14px;
                        line-height: 1.6;
                        color: #6b7280;
                        margin: 0 0 12px;
                    "
                >
                    This activation link will expire in
                    <strong>
                        {settings.ACTIVATION_TOKEN_EXPIRES_HOURS} hours
                    </strong>.
                </p>

                <p
                    style="
                        font-size: 13px;
                        line-height: 1.6;
                        color: #9ca3af;
                        margin: 24px 0 0;
                    "
                >
                    If you were not expecting this email, you can safely ignore it.
                </p>
            </div>

            <p
                style="
                    text-align: center;
                    font-size: 12px;
                    color: #9ca3af;
                    margin-top: 20px;
                "
            >
                © LFGS | Meridian
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html


async def send_activation_email(
    to_email: str,
    username: str,
    raw_activation_token: str,
) -> None:
    subject, html = build_activation_email(
        activation_token=raw_activation_token,
        username=username,
    )

    await send_email(
        subject=subject,
        to_email=to_email,
        html_body=html,
    )
