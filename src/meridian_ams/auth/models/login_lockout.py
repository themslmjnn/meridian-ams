from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meridian_ams.database.base import Base, CreatedAtMixin, IdMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from meridian_ams.users.models.credentials import UserCredentials


class UserLoginLockout(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "user_login_lockouts"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    failed_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    credentials: Mapped["UserCredentials"] = relationship(
        back_populates="login_lockout"
    )
