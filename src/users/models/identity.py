from datetime import date

from sqlalchemy import Enum, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase
from src.users.utils.enums import UserRole


class UserIdentity(MutableBase):
    __tablename__ = "user_identities"

    firstname: Mapped[str] = mapped_column(String(50), nullable=False)
    lastname: Mapped[str] = mapped_column(String(50), nullable=False)
    middlename: Mapped[str | None] = mapped_column(String(50), nullable=True)

    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)
    address: Mapped[str | None] = mapped_column(String(100), nullable=True)

    phone_number: Mapped[str] = mapped_column(String(25), nullable=False)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)

    credentials: Mapped[list["UserCredentials"]] = relationship(  # type: ignore  # noqa: F821
        back_populates="identity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "uix_non_student_unique_phone",
            "phone_number",
            unique=True,
            postgresql_where=text("role <> 'STUDENT'"),
        ),
        Index(
            "ix_gin_identity_firstname",
            "firstname",
            postgresql_using="gin",
            postgresql_ops={"firstname": "gin_trgm_ops"},
        ),
        Index(
            "ix_gin_identity_lastname",
            "lastname",
            postgresql_using="gin",
            postgresql_ops={"lastname": "gin_trgm_ops"},
        ),
    )
