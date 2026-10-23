import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import MutableBase


class Group(MutableBase):
    __tablename__ = "groups"

    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(20), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    grade_level: Mapped[int] = mapped_column(nullable=False)
    max_capacity: Mapped[int] = mapped_column(nullable=False, default=30)

    is_archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignments: Mapped[list["StudentGroupAssignment"]] = relationship(
        back_populates="group"
    )

    __table_args__ = (
        UniqueConstraint(
            "name", "academic_year", name="uix_group_name_per_academic_year"
        ),
    )


class StudentGroupAssignment(MutableBase):
    __tablename__ = "student_group_assignments"

    student_credentials_id: Mapped[int] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    group: Mapped["Group"] = relationship(back_populates="assignments")

    __table_args__ = (
        Index(
            "ix_active_student_group",
            "student_credentials_id",
            postgresql_where=text("unassigned_at IS NULL"),
        ),
        Index(
            "uix_one_active_group_per_student",
            "student_credentials_id",
            unique=True,
            postgresql_where=text("unassigned_at IS NULL"),
        ),
        Index("ix_student_group_assignment_group_id", "group_id"),
    )
