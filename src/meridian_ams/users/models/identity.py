from datetime import date

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from meridian_ams.database.base import Base, CreatedAtMixin, IdMixin, UpdatedAtMixin


class UserIdentity(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "user_identities"

    first_name: Mapped[str] = mapped_column(String(30), nullable=False)
    last_name: Mapped[str] = mapped_column(String(30), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(30), nullable=True)

    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)
    address: Mapped[str | None] = mapped_column(String(150), nullable=True)

    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index(
            "ix_gin_identity_first_name",
            "first_name",
            postgresql_using="gin",
            postgresql_ops={"first_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_gin_identity_last_name",
            "last_name",
            postgresql_using="gin",
            postgresql_ops={"last_name": "gin_trgm_ops"},
        ),
    )
