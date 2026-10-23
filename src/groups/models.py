import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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

    __table_args__ = (
        UniqueConstraint(
            "name", "academic_year", name="uix_group_name_per_academic_year"
        ),
    )
