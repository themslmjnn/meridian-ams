from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.connection import ImmutableBase
from src.utils.enums import IdempotencyStatus


class IdempotencyRecord(ImmutableBase):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[int] = mapped_column(nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[IdempotencyStatus] = mapped_column(
        nullable=False, default=IdempotencyStatus.PROCESSING
    )
    http_status: Mapped[int | None] = mapped_column(nullable=True)

    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (UniqueConstraint("key", name="uix_idempotency_key"),)
