from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    # mac_address and ip_address are nullable starting feature 016 — HA-only
    # devices (Thread/Zigbee endpoints) have no LAN MAC or IP. Uniqueness for
    # scanner-discovered devices is preserved via the partial unique index
    # devices_mac_address_unique on non-null values. A CHECK constraint
    # (devices_identifier_present) guarantees at least mac_address OR
    # ha_device_id is set, so no anonymous rows can exist.
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(15), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    is_online: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    consecutive_missed_scans: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    is_known_device: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    monitor_offline: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    # Enrichment columns
    os_family: Mapped[str | None] = mapped_column(String(50), nullable=True)
    os_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mdns_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    netbios_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssdp_friendly_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssdp_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    enrichment_ip: Mapped[str | None] = mapped_column(String(15), nullable=True)

    # Home Assistant provenance (feature 016).
    # ha_device_id is HA's per-device UUID — stable across HA restarts and
    # entity renames; the canonical join key for HA-sourced rows.
    ha_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ha_connectivity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ha_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    annotation: Mapped["Annotation"] = relationship(  # noqa: F821
        back_populates="device", uselist=False, cascade="all, delete-orphan"
    )
    services: Mapped[list["Service"]] = relationship(  # noqa: F821
        back_populates="device", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="device")  # noqa: F821
    events: Mapped[list["Event"]] = relationship(  # noqa: F821
        back_populates="device"
    )
