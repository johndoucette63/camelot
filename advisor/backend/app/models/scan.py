from datetime import datetime

from sqlalchemy import Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    devices_found: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    new_devices: Mapped[int | None] = mapped_column(Integer(), nullable=True, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text(), nullable=True)

    events: Mapped[list["Event"]] = relationship(back_populates="scan")  # noqa: F821
