from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase
from src.guardian_links.utils.enums import GuardianType

if TYPE_CHECKING:
    from src.users.models.credentials import UserCredentials


class StudentGuardianLink(MutableBase):
    __tablename__ = "student_guardian_links"

    student_credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"), nullable=False
    )
    guardian_credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guardian_type: Mapped[GuardianType] = mapped_column(
        Enum(GuardianType), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "student_credentials_id",
            "guardian_type",
            name="uix_one_guardian_type_per_student",
        ),
        UniqueConstraint(
            "student_credentials_id",
            "guardian_credentials_id",
            name="uix_no_duplicate_guardian_link",
        ),
    )

    student: Mapped["UserCredentials"] = relationship(
        foreign_keys=[student_credentials_id]
    )
    guardian: Mapped["UserCredentials"] = relationship(
        foreign_keys=[guardian_credentials_id]
    )
