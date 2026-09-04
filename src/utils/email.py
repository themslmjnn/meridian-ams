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


async def send_email_safe(coro, **log_context) -> None:
    """
    Fire-and-forget send. Swallows all exceptions and logs them as warnings.
    Use for informational emails where delivery failure is acceptable
    and no retry or DB record is needed.

    Never use this inside the worker — the worker needs exceptions to surface
    so it can record failures and drive retry logic.
    """
    try:
        await coro

    except Exception as exc:
        logger.error(
            "background_email_task_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            **log_context,
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


async def send_account_info_updated_email(email: str) -> None:
    subject = "Your account information has been updated"

    html = """
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
                    Meridian
                </h1>

                <h2
                    style="
                        margin: 0 0 20px;
                        font-size: 20px;
                        color: #1f2937;
                    "
                >
                    Your account information has been updated
                </h2>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    Hello,
                </p>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    A school administrator has updated some information
                    associated with your account.
                </p>

                <div
                    style="
                        margin: 28px 0;
                        padding: 16px;
                        background-color: #f9fafb;
                        border-radius: 6px;
                    "
                >
                    <p
                        style="
                            margin: 0;
                            font-size: 14px;
                            line-height: 1.6;
                            color: #6b7280;
                        "
                    >
                        If you were expecting this update, no further action
                        is required.
                    </p>
                </div>

                <p
                    style="
                        font-size: 14px;
                        line-height: 1.6;
                        color: #6b7280;
                        margin: 24px 0 0;
                    "
                >
                    If you did not expect this change, please contact your
                    school administration as soon as possible.
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
                © Meridian
            </p>
        </div>
    </body>
    </html>
    """

    await send_email(
        subject=subject,
        to_email=email,
        html_body=html,
    )


def build_admin_credentials_override_notification_email(
    old_username: str | None = None,
    new_username: str | None = None,
    old_email: str | None = None,
    new_email: str | None = None,
) -> tuple[str, str]:
    changes_html = ""

    subject = "Your Meridian account credentials were changed"
    login_link = f"{settings.APP_URL}/auth/login"

    if old_username is not None and new_username is not None:
        changes_html += f"""
            <tr>
                <td
                    style="
                        padding: 10px 0;
                        color: #6b7280;
                        font-size: 14px;
                    "
                >
                    Old username
                </td>
                <td
                    style="
                        padding: 10px 0;
                        font-weight: bold;
                        color: #374151;
                    "
                >
                    {old_username}
                </td>
            </tr>

            <tr>
                <td
                    style="
                        padding: 10px 0;
                        color: #6b7280;
                        font-size: 14px;
                    "
                >
                    New username
                </td>
                <td
                    style="
                        padding: 10px 0;
                        font-weight: bold;
                        color: #374151;
                    "
                >
                    {new_username}
                </td>
            </tr>
        """

    if old_email is not None and new_email is not None:
        changes_html += f"""
            <tr>
                <td
                    style="
                        padding: 10px 0;
                        color: #6b7280;
                        font-size: 14px;
                    "
                >
                    Old email
                </td>
                <td
                    style="
                        padding: 10px 0;
                        font-weight: bold;
                        color: #374151;
                    "
                >
                    {old_email}
                </td>
            </tr>

            <tr>
                <td
                    style="
                        padding: 10px 0;
                        color: #6b7280;
                        font-size: 14px;
                    "
                >
                    New email
                </td>
                <td
                    style="
                        padding: 10px 0;
                        font-weight: bold;
                        color: #374151;
                    "
                >
                    {new_email}
                </td>
            </tr>
        """

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
                    Meridian
                </h1>

                <h2
                    style="
                        margin: 0 0 20px;
                        font-size: 20px;
                        color: #1f2937;
                    "
                >
                    Your account credentials were changed
                </h2>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    An administrator has updated the credentials associated
                    with your account.
                </p>

                <div
                    style="
                        margin: 24px 0;
                        padding: 16px 20px;
                        background-color: #f9fafb;
                        border-radius: 6px;
                    "
                >
                    <table
                        style="
                            width: 100%;
                            border-collapse: collapse;
                        "
                    >
                        {changes_html}
                    </table>
                </div>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    If you were expecting this change, no further action is
                    required. You will need to log in again using your new
                    credentials.
                </p>

                <div style="text-align: center; margin: 32px 0;">
                    <a
                        href="{login_link}"
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
                        Log In
                    </a>
                </div>

                <p
                    style="
                        font-size: 14px;
                        line-height: 1.6;
                        color: #6b7280;
                        margin: 24px 0 0;
                    "
                >
                    If you were not expecting this change, please contact your
                    administrator as soon as possible.
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
                © Meridian
            </p>
        </div>
    </body>
    </html>
    """

    return subject, html


async def send_admin_credentials_override_notification(
    email: str,
    old_username: str | None = None,
    new_username: str | None = None,
    old_email: str | None = None,
    new_email: str | None = None,
) -> None:
    subject, html = build_admin_credentials_override_notification_email(
        old_username=old_username,
        new_username=new_username,
        old_email=old_email,
        new_email=new_email,
    )

    await send_email(
        subject=subject,
        to_email=email,
        html_body=html,
    )


async def send_account_deactivation_email(email: str) -> None:
    subject = "Your Meridian account has been deactivated"

    html = """
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
                    Meridian
                </h1>

                <h2
                    style="
                        margin: 0 0 20px;
                        font-size: 20px;
                        color: #1f2937;
                    "
                >
                    Your account has been deactivated
                </h2>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    An administrator has deactivated your account.
                </p>

                <div
                    style="
                        margin: 24px 0;
                        padding: 16px;
                        background-color: #f9fafb;
                        border-radius: 6px;
                    "
                >
                    <p
                        style="
                            margin: 0;
                            font-size: 14px;
                            line-height: 1.6;
                            color: #6b7280;
                        "
                    >
                        You will no longer be able to access your account
                        while it remains deactivated.
                    </p>
                </div>

                <p
                    style="
                        font-size: 14px;
                        line-height: 1.6;
                        color: #6b7280;
                        margin: 24px 0 0;
                    "
                >
                    If you believe this was done in error, please contact
                    your school administrator.
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
                © Meridian
            </p>
        </div>
    </body>
    </html>
    """

    await send_email(
        subject=subject,
        to_email=email,
        html_body=html,
    )


async def send_account_activation_email(email: str) -> None:
    login_link = f"{settings.APP_URL}/auth/login"

    subject = "Your Meridian account has been activated"

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
                    Meridian
                </h1>

                <h2
                    style="
                        margin: 0 0 20px;
                        font-size: 20px;
                        color: #1f2937;
                    "
                >
                    Your account has been activated
                </h2>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    An administrator has activated your account.
                    You can now log in and access the system.
                </p>

                <div style="text-align: center; margin: 32px 0;">
                    <a
                        href="{login_link}"
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
                        Log In
                    </a>
                </div>

                <p
                    style="
                        font-size: 14px;
                        line-height: 1.6;
                        color: #6b7280;
                        margin: 24px 0 0;
                    "
                >
                    If you were not expecting this, please contact your
                    administrator as soon as possible.
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
                © Meridian
            </p>
        </div>
    </body>
    </html>
    """

    await send_email(
        subject=subject,
        to_email=email,
        html_body=html,
    )


def build_reset_password_email(
    reset_password_token: str,
) -> tuple[str, str]:
    reset_link = f"{settings.APP_URL}/auth/reset-password?token={reset_password_token}"

    subject = "Your Meridian password reset link"

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
                        Meridian
                    </h1>

                    <h2
                        style="
                            margin: 0 0 20px;
                            font-size: 20px;
                            color: #1f2937;
                        "
                    >
                        Reset your password
                    </h2>

                    <p style="line-height: 1.6; margin: 0 0 16px;">
                        An administrator has requested a password reset for your
                        account.
                    </p>

                    <p style="line-height: 1.6; margin: 0 0 16px;">
                        Click the button below to create a new password.
                    </p>

                    <div style="text-align: center; margin: 32px 0;">
                        <a
                            href="{reset_link}"
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
                            Reset Password
                        </a>
                    </div>

                    <div
                        style="
                            margin: 24px 0;
                            padding: 16px;
                            background-color: #f9fafb;
                            border-radius: 6px;
                        "
                    >
                        <p
                            style="
                                margin: 0;
                                font-size: 14px;
                                line-height: 1.6;
                                color: #6b7280;
                            "
                        >
                            This password reset link will expire in
                            <strong>
                                {settings.RESET_PASSWORD_EXPIRES_MINUTES} minutes
                            </strong>.
                        </p>
                    </div>

                    <p
                        style="
                            font-size: 14px;
                            line-height: 1.6;
                            color: #6b7280;
                            margin: 24px 0 0;
                        "
                    >
                        If you were not expecting this request, please contact
                        your administrator as soon as possible.
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
                    © Meridian
                </p>
            </div>
        </body>
        </html>
        """

    return subject, html


async def send_reset_password_token(
    email: str,
    raw_reset_token: str,
) -> None:
    subject, html = build_reset_password_email(raw_reset_token)

    await send_email(
        subject=subject,
        to_email=email,
        html_body=html,
    )


async def send_account_deletion_email(email: str) -> None:
    login_link = f"{settings.APP_URL}/auth/login"

    subject = "Your Meridian account is scheduled for deletion"

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
                    Meridian
                </h1>

                <h2
                    style="
                        margin: 0 0 20px;
                        font-size: 20px;
                        color: #1f2937;
                    "
                >
                    Your account is scheduled for deletion
                </h2>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    A school administrator has scheduled your account for
                    deletion.
                </p>

                <div
                    style="
                        margin: 24px 0;
                        padding: 16px;
                        background-color: #f9fafb;
                        border-radius: 6px;
                    "
                >
                    <p
                        style="
                            margin: 0;
                            font-size: 14px;
                            line-height: 1.6;
                            color: #6b7280;
                        "
                    >
                        Your account will be
                        <strong>permanently deleted in 30 days</strong>.
                    </p>
                </div>

                <p style="line-height: 1.6; margin: 0 0 16px;">
                    You can still log in and use your account normally during
                    this 30-day period.
                </p>

                <div style="text-align: center; margin: 32px 0;">
                    <a
                        href="{login_link}"
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
                        Log In
                    </a>
                </div>

                <p
                    style="
                        font-size: 14px;
                        line-height: 1.6;
                        color: #6b7280;
                        margin: 24px 0 0;
                    "
                >
                    If you believe this was done in error, please contact your
                    school administrator before the deletion date.
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
                © Meridian
            </p>
        </div>
    </body>
    </html>
    """

    await send_email(
        subject=subject,
        to_email=email,
        html_body=html,
    )
