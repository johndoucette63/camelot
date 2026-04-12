from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RejectedSuggestion(Base):
    __tablename__ = "rejected_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer(), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
