from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolution_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="rule")
    suppressed: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    # Outbound delivery retry state (feature 016 — FR-019, FR-020).
    # delivery_status: pending | sent | failed | suppressed | terminal | n/a
    # delivery_next_attempt_at drives the retry-sweep picker; null when
    # no retry is scheduled.
    delivery_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    delivery_attempt_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0
    )
    delivery_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    device: Mapped["Device | None"] = relationship(back_populates="alerts")  # noqa: F821
    service: Mapped["Service | None"] = relationship()  # noqa: F821
