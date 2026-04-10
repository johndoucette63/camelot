from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")  # noqa: F821
