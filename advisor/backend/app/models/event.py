from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    device_id: Mapped[int | None] = mapped_column(
        Integer(), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    scan_id: Mapped[int | None] = mapped_column(
        Integer(), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    details: Mapped[dict | None] = mapped_column(JSON(), nullable=True)

    device: Mapped["Device | None"] = relationship(back_populates="events")  # noqa: F821
    scan: Mapped["Scan | None"] = relationship(back_populates="events")  # noqa: F821
