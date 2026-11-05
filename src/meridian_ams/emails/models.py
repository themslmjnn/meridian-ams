from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meridian_ams.database.base import (
    Base,
    CreatedAtMixin,
    IdMixin,
    PublicIdMixin,
    UpdatedAtMixin,
)
from meridian_ams.emails.enums import EmailStatus, EmailType

if TYPE_CHECKING:
    from meridian_ams.users.models.credentials import UserCredentials


class Email(IdMixin, PublicIdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "emails"

    recipient_email: Mapped[str] = mapped_column(String(50), nullable=False)

    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)

    email_type: Mapped[EmailType] = mapped_column(
        Enum(EmailType), nullable=False, index=True
    )

    status: Mapped[EmailStatus] = mapped_column(
        Enum(EmailStatus),
        nullable=False,
        server_default=EmailStatus.PENDING.name,
        index=True,
    )

    retry_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    max_retries: Mapped[int] = mapped_column(nullable=False, server_default="3")

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_by: Mapped[int | None] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    triggered_by_user: Mapped["UserCredentials | None"] = relationship(
        "UserCredentials",
        foreign_keys=[triggered_by],
    )
