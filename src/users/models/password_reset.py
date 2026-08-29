from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase


class UserPasswordReset(MutableBase):
    __tablename__ = "user_password_resets"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    reset_password_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    reset_password_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    credentials: Mapped["UserCredentials"] = relationship(  # noqa: F821
        back_populates="password_reset"
    )
