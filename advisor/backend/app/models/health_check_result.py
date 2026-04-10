from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HealthCheckResult(Base):
    __tablename__ = "health_check_results"
    __table_args__ = (
        Index(
            "idx_hcr_service_checked",
            "service_id",
            "checked_at",
            postgresql_ops={"checked_at": "DESC"},
        ),
        Index("idx_hcr_checked_at", "checked_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("service_definitions.id", ondelete="CASCADE"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    service_definition: Mapped["ServiceDefinition"] = relationship(  # noqa: F821
        back_populates="health_check_results"
    )
