from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from meridian_ams.core.idempotency.utils.enums import IdempotencyStatus
from meridian_ams.database.base import Base, CreatedAtMixin, IdMixin


class IdempotencyRecord(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[int] = mapped_column(nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    http_status: Mapped[int] = mapped_column(nullable=False)

    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "operation",
            "actor_id",
            "key",
            name="uix_idempotency_operation_actor_key",
        ),
    )
