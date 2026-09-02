from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase


class UserSession(MutableBase):
    __tablename__ = "user_sessions"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_token_version: Mapped[int] = mapped_column(nullable=False, default=1)

    refresh_token_hash: Mapped[str | None] = mapped_column(nullable=True)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refresh_token_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_refresh_token_hash: Mapped[str | None] = mapped_column(nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    credentials: Mapped["UserCredentials"] = relationship(  # noqa: F821
        back_populates="sessions"
    )
