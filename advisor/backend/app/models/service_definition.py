from datetime import datetime

from sqlalchemy import Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ServiceDefinition(Base):
    __tablename__ = "service_definitions"
    __table_args__ = (
        UniqueConstraint("name", "host", name="uq_service_name_host"),
        Index("idx_service_definitions_host_label", "host_label"),
        Index("idx_service_definitions_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    host_label: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer(), nullable=False)
    check_type: Mapped[str] = mapped_column(String(10), nullable=False)
    check_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    check_interval_seconds: Mapped[int] = mapped_column(
        Integer(), nullable=False, server_default="60"
    )
    degraded_threshold_ms: Mapped[int | None] = mapped_column(
        Integer(), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    health_check_results: Mapped[list["HealthCheckResult"]] = relationship(  # noqa: F821
        back_populates="service_definition", cascade="all, delete-orphan"
    )
