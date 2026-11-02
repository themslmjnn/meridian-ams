from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meridian_ams.database.base import (
    Base,
    CreatedAtMixin,
    IdMixin,
    PublicIdMixin,
    UpdatedAtMixin,
)
from meridian_ams.users.utils.enums import AccountType, UserRole, UserStatus

if TYPE_CHECKING:
    from meridian_ams.users.models.identity import UserIdentity


class UserCredentials(IdMixin, PublicIdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "user_credentials"

    identity_id: Mapped[int] = mapped_column(
        ForeignKey("user_identities.id", ondelete="CASCADE"), nullable=False
    )

    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(50), nullable=False)

    password_hash: Mapped[str | None] = mapped_column(nullable=True)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.PENDING_ACTIVATION
    )
    pre_transition_status: Mapped[UserStatus | None] = mapped_column(nullable=True)

    identity: Mapped["UserIdentity"] = relationship(back_populates="credentials")

    __table_args__ = (
        Index(
            "uix_non_student_unique_email",
            "email",
            unique=True,
            postgresql_where=text("account_type != 'STUDENT'"),
        ),
        Index(
            "uix_one_personal_account_per_identity",
            "identity_id",
            unique=True,
            postgresql_where=text("account_type = 'PERSONAL'"),
        ),
        Index(
            "ix_gin_credentials_email",
            "email",
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
        ),
    )
