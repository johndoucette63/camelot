from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    tags: Mapped[list] = mapped_column(
        JSON(), nullable=False, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('device', 'service', 'playbook')",
            name="notes_target_type_check",
        ),
        Index("idx_notes_target", "target_type", "target_id"),
        Index("idx_notes_pinned", "pinned", "target_type"),
        Index("idx_notes_updated_at", updated_at.desc()),
    )
