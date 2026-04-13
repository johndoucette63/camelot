from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    mac_address: Mapped[str] = mapped_column(String(17), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(15), nullable=False)
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
