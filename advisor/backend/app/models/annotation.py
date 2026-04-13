from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        Integer(), ForeignKey("devices.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tags: Mapped[list] = mapped_column(
        JSON(), nullable=False, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Classification columns
    classification_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    classification_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)

    device: Mapped["Device"] = relationship(back_populates="annotation")  # noqa: F821
