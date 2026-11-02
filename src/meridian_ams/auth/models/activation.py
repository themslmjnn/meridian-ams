from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meridian_ams.database.base import Base, CreatedAtMixin, IdMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from meridian_ams.users.models.credentials import UserCredentials


class UserActivation(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
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

    credentials: Mapped["UserCredentials"] = relationship(back_populates="activation")
