from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase
from src.emails.utils.enums import EmailStatus, EmailType


class Email(MutableBase):
    __tablename__ = "emails"

    recipient_email: Mapped[str] = mapped_column(String(100), nullable=False)

    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)

    email_type: Mapped[EmailType] = mapped_column(
        Enum(EmailType), nullable=False, index=True
    )

    status: Mapped[EmailStatus] = mapped_column(
        Enum(EmailStatus),
        nullable=False,
        default=EmailStatus.PENDING,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    triggered_by: Mapped[int | None] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    triggered_by_user: Mapped["UserCredentials | None"] = relationship(  # noqa: F821
        "UserCredentials",
        foreign_keys=[triggered_by],
    )
