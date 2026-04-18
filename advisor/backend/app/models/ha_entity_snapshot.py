"""Per-entity snapshot row from the HA poll (feature 016)."""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Production runs on Postgres and gets JSONB (per data-model.md); SQLite
# used by the pytest suite falls back to the dialect-neutral JSON type.
_AttributesType = JSON().with_variant(JSONB(), "postgresql")


class HAEntitySnapshot(Base):
    __tablename__ = "ha_entity_snapshots"

    entity_id: Mapped[str] = mapped_column(Text, primary_key=True)
    ha_device_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    friendly_name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    last_changed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        _AttributesType, nullable=False, default=dict
    )
    polled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
