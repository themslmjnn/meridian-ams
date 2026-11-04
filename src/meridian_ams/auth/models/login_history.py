from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meridian_ams.database.base import Base, CreatedAtMixin, IdMixin

if TYPE_CHECKING:
    from meridian_ams.users.models.credentials import UserCredentials


class LoginHistory(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "login_history"

    credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    credentials: Mapped["UserCredentials"] = relationship(
        back_populates="login_history"
    )
