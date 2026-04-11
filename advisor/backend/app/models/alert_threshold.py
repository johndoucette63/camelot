from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlertThreshold(Base):
    __tablename__ = "alert_thresholds"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    default_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    min_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    max_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
