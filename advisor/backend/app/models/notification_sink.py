from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationSink(Base):
    __tablename__ = "notification_sinks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Known types: "webhook" (existing, free-form URL) and "home_assistant"
    # (feature 016 — endpoint holds the bare notify-service suffix like
    # "mobile_app_pixel9"; base URL + bearer token are resolved via
    # home_assistant_id -> home_assistant_connections).
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    endpoint: Mapped[str] = mapped_column(Text(), nullable=False)
    min_severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="critical"
    )
    home_assistant_id: Mapped[int | None] = mapped_column(
        Integer(),
        ForeignKey("home_assistant_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
