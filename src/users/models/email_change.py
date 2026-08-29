from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase


class UserEmailChange(MutableBase):
    __tablename__ = "user_email_changes"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    new_email: Mapped[str] = mapped_column(String(100), nullable=False)
    email_change_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_change_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    credentials: Mapped["UserCredentials"] = relationship(  # noqa: F821
        back_populates="email_change"
    )
