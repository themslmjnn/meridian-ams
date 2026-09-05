from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import ImmutableBase


class LoginHistory(ImmutableBase):
    __tablename__ = "login_history"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    credentials: Mapped["UserCredentials"] = relationship(  # noqa: F821
        back_populates="login_history"
    )


class LoginHistorySummary(ImmutableBase):
    __tablename__ = "login_history_summary"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary_date: Mapped[date] = mapped_column(nullable=False)
    successful_logins: Mapped[int] = mapped_column(default=0, nullable=False)
    failed_logins: Mapped[int] = mapped_column(default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "credentials_id",
            "summary_date",
            name="uix_login_summary_per_day",
        ),
    )
