"""Thread border router derived from HA's thread integration (feature 016)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ThreadBorderRouter(Base):
    __tablename__ = "thread_border_routers"

    ha_device_id: Mapped[str] = mapped_column(Text, primary_key=True)
    friendly_name: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attached_device_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
