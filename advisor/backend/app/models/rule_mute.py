from datetime import datetime

from sqlalchemy import Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RuleMute(Base):
    __tablename__ = "rule_mutes"
    __table_args__ = (
        Index(
            "idx_rule_mutes_lookup",
            "rule_id",
            "target_type",
            "target_id",
            "expires_at",
            "cancelled_at",
            postgresql_ops={"expires_at": "DESC"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
