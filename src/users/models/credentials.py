import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase
from src.users.utils.enums import AccountType, UserRole, UserStatus


class UserCredentials(MutableBase):
    __tablename__ = "user_credentials"

    identity_id: Mapped[int] = mapped_column(
        ForeignKey("user_identities.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )

    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(50), nullable=False)

    password_hash: Mapped[str | None] = mapped_column(nullable=True)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.PENDING_ACTIVATION
    )
    deletion_scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    pre_deletion_status: Mapped[UserStatus | None] = mapped_column(nullable=True)

    identity: Mapped["UserIdentity"] = relationship(back_populates="credentials")  # type: ignore # noqa: F821

    activation: Mapped["UserActivation | None"] = relationship(  # noqa: F821
        back_populates="credentials",
        cascade="all, delete-orphan",
        uselist=False,
    )
    sessions: Mapped[list["UserSession"]] = relationship(  # noqa: F821
        back_populates="credentials",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "uix_non_student_unique_email",
            "email",
            unique=True,
            postgresql_where=text("account_type != 'STUDENT'"),
        ),
        Index(
            "ix_gin_credentials_email",
            "email",
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
        ),
    )
