from html import escape

from meridian_ams.core.config import get_settings
from meridian_ams.core.email.service import send_email


def build_account_activation_email(
    username: str, raw_activation_token: str
) -> tuple[str, str]:
    settings = get_settings()

    activation_link = f"{settings.APP_URL}/activation?token={raw_activation_token}"

    subject = "Activate your Meridian account"

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

    return subject, html_body


async def send_account_activation_email(
    *,
    to_email: str,
    username: str,
    raw_activation_token: str,
) -> None:
    subject, html_body = build_account_activation_email(
        raw_activation_token=raw_activation_token,
        username=username,
    )

    await send_email(
        subject=subject,
        to_email=to_email,
        html_body=html_body,
    )


def build_new_login_notification_email(
    user_agent: str, login_time: str
) -> tuple[str, str]:
    subject = "New login to your Meridian account"

    html_body = f"""
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
                        New login detected
                    </h2>

                    <p style="
                        margin:0 0 16px;
                        line-height:1.6;
                    ">
                        A new login to your Meridian account was detected.
                    </p>

                    <div style="
                        margin:24px 0;
                        padding:16px;
                        background-color:#f9fafb;
                        border-radius:6px;
                    ">
                        <table style="
                            width:100%;
                            border-collapse:collapse;
                            font-size:14px;
                        ">
                            <tr>
                                <td style="
                                    padding:6px 0;
                                    color:#6b7280;
                                    width:90px;
                                    vertical-align:top;
                                ">
                                    Time
                                </td>
                                <td style="
                                    padding:6px 0;
                                    color:#374151;
                                    line-height:1.5;
                                ">
                                    {escape(login_time)}
                                </td>
                            </tr>
                            <tr>
                                <td style="
                                    padding:6px 0;
                                    color:#6b7280;
                                    vertical-align:top;
                                ">
                                    Device
                                </td>
                                <td style="
                                    padding:6px 0;
                                    color:#374151;
                                    line-height:1.5;
                                    word-break:break-word;
                                ">
                                    {escape(user_agent)}
                                </td>
                            </tr>
                        </table>
                    </div>

                    <p style="
                        margin:0 0 16px;
                        line-height:1.6;
                    ">
                        If you made this login, no further action is needed.
                    </p>

                    <p style="
                        margin:0 0 24px;
                        line-height:1.6;
                    ">
                        If you do not recognize this login, reset your password
                        immediately and contact your administrator.
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

    return subject, html_body


async def send_new_login_notification_email(
    *,
    to_email: str,
    user_agent: str,
    login_time: str,
) -> None:
    subject, html_body = build_new_login_notification_email(
        user_agent,
        login_time,
    )

    await send_email(
        subject=subject,
        to_email=to_email,
        html_body=html_body,
    )
