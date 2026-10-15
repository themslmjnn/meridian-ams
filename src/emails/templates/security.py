from src.core.email.service import send_email


async def send_password_changed_confirmation(to_email: str) -> None:
    subject = "Your Meridian password was changed"

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
                        Your password was changed
                    </h2>

                    <p style="line-height: 1.6; margin: 0 0 16px;">
                        Your account password was successfully changed.
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
                            If you made this change, no further action is needed.
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
                        If you did not change your password, please contact your
                        administrator immediately, as your account may be compromised.
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
