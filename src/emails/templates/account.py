from src.core.config import get_settings
from src.core.email.service import send_email

settings = get_settings()


async def send_admin_profile_override_email(to_email: str) -> None:
    subject = "Your account information has been updated"

    html_body = """
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
        to_email=to_email,
        html_body=html_body,
    )


def build_admin_credentials_override_email(
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

    html_body = f"""
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

    return subject, html_body


async def send_admin_credentials_override_notification(
    to_email: str,
    old_username: str | None = None,
    new_username: str | None = None,
    old_email: str | None = None,
    new_email: str | None = None,
) -> None:
    subject, html_body = build_admin_credentials_override_email(
        old_username=old_username,
        new_username=new_username,
        old_email=old_email,
        new_email=new_email,
    )

    await send_email(
        subject=subject,
        to_email=to_email,
        html_body=html_body,
    )


async def send_admin_account_deactivation_email(to_email: str) -> None:
    subject = "Your Meridian account has been deactivated"

    html_body = """
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
        to_email=to_email,
        html_body=html_body,
    )


async def send_admin_account_activation_email(to_email: str) -> None:
    login_link = f"{settings.APP_URL}/auth/login"

    subject = "Your Meridian account has been activated"

    html_body = f"""
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
        to_email=to_email,
        html_body=html_body,
    )


async def send_email_change_email(new_email: str, raw_email_change_token: str) -> None:
    email_change_page_link = (
        f"{settings.APP_URL}/users/me/credentials/confirm-email"
        f"?token={raw_email_change_token}"
    )

    subject = "Confirm your new Meridian email address"

    html_body = f"""
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
                        Confirm your new email address
                    </h2>

                    <p style="line-height: 1.6; margin: 0 0 16px;">
                        You requested to change your email address to
                        <strong>{new_email}</strong>.
                        Confirm your new address using the button below.
                    </p>

                    <div style="text-align: center; margin: 32px 0;">
                        <a
                            href="{email_change_page_link}"
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
                            Confirm email address
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
                            This confirmation link will expire in
                            <strong>
                                {settings.EMAIL_CHANGE_TOKEN_EXPIRES_MINUTES}
                                minutes
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
                        If you did not request this change, you can safely ignore
                        this email. Your current email address has not been changed.
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
        to_email=new_email,
        html_body=html_body,
    )


async def send_email_changed_confirmation_email(old_email: str, new_email: str) -> None:
    subject = "Your Meridian account email was changed"

    html_body = f"""
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
                        Your email address was changed
                    </h2>

                    <p style="line-height: 1.6; margin: 0 0 16px;">
                        The email address associated with your account was
                        recently changed.
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
                        </table>
                    </div>

                    <p style="line-height: 1.6; margin: 0 0 16px;">
                        If you made this change, no further action is needed.
                    </p>

                    <p
                        style="
                            font-size: 14px;
                            line-height: 1.6;
                            color: #6b7280;
                            margin: 24px 0 0;
                        "
                    >
                        If you did not request this change, please contact your
                        school administrator immediately.
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
        to_email=old_email,
        html_body=html_body,
    )


async def send_guardian_deletion_email(to_email: str) -> None:
    login_link = f"{settings.APP_URL}/auth/login"

    subject = "Your Meridian account is scheduled for deletion"

    html_body = f"""
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
        to_email=to_email,
        html_body=html_body,
    )


async def send_admin_account_deletion_cancellation_email(to_email: str) -> None:
    login_link = f"{settings.APP_URL}/auth/login"

    subject = "Your Meridian account deletion has been canceled"

    html_body = f"""
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
                        Your account deletion has been canceled
                    </h2>

                    <p style="line-height: 1.6; margin: 0 0 16px;">
                        The scheduled deletion of your account has been
                        <strong>canceled</strong> by a school administrator.
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
                            Your account remains active. You can continue logging
                            in and using Meridian as normal.
                        </p>
                    </div>

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
                        If you have any questions, please contact your school
                        administrator.
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
        to_email=to_email,
        html_body=html_body,
    )


async def send_profile_updated_confirmation(to_email: str) -> None:
    subject = "Your Meridian profile was changed"

    html_body = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="
            margin:0;
            padding:0;
            font-family:Arial,sans-serif;
            background-color:#f5f6f8;
            color:#374151;
        ">
            <div style="padding:40px 20px;">
                <div style="
                    max-width:560px;
                    margin:0 auto;
                    background-color:#ffffff;
                    border-radius:10px;
                    padding:40px;
                    box-sizing:border-box;
                ">
                    <h1 style="
                        margin:0 0 30px;
                        font-size:22px;
                        color:#1f2937;
                    ">
                        Meridian
                    </h1>

                    <h2 style="
                        margin:0 0 20px;
                        font-size:20px;
                        color:#1f2937;
                    ">
                        Your profile was changed
                    </h2>

                    <p style="
                        margin:0 0 16px;
                        line-height:1.6;
                    ">
                        Your Meridian profile information was successfully changed.
                    </p>

                    <div style="
                        margin:24px 0;
                        padding:16px;
                        background-color:#f9fafb;
                        border-radius:6px;
                    ">
                        <p style="
                            margin:0;
                            font-size:14px;
                            line-height:1.6;
                            color:#6b7280;
                        ">
                            If you made this change, no further action is needed.
                        </p>
                    </div>

                    <p style="
                        margin:0;
                        line-height:1.6;
                    ">
                        If you did not make this change, please contact your
                        administrator as soon as possible.
                    </p>
                </div>

                <p style="
                    text-align:center;
                    font-size:12px;
                    color:#9ca3af;
                    margin-top:20px;
                ">
                    © Meridian
                </p>
            </div>
        </body>
        </html>
    """

    await send_email(
        subject=subject,
        to_email=to_email,
        html_body=html_body,
    )
