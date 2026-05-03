from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InfraUpdate(Base):
    __tablename__ = "infra_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    stack_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    output: Mapped[str] = mapped_column(Text(), nullable=False, server_default="")
    exit_code: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'failed', 'timeout')",
            name="infra_updates_status_check",
        ),
        Index("idx_infra_updates_stack_started", "stack_key", started_at.desc()),
    )
