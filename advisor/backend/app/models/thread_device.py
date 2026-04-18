"""Thread end-device derived from HA's thread integration (feature 016)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ThreadDevice(Base):
    __tablename__ = "thread_devices"

    ha_device_id: Mapped[str] = mapped_column(Text, primary_key=True)
    friendly_name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_border_router_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("thread_border_routers.ha_device_id", ondelete="SET NULL"),
        nullable=True,
    )
    online: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Preserved across refreshes so the UI can say "last connected via X"
    # even after the device drops off entirely.
    last_seen_parent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
