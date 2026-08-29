from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase


class UserActivation(MutableBase):
    __tablename__ = "user_activations"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    activation_token_hash: Mapped[str] = mapped_column(nullable=False)
    activation_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    credentials: Mapped["UserCredentials"] = relationship(back_populates="activation")  # type: ignore  # noqa: F821, UP037
