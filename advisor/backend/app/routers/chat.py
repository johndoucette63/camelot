"""Chat router — conversation CRUD + streaming advisor responses.

Exposes four endpoints (see specs/010-ai-advisor-chat/contracts/chat-api.md):
    GET    /chat/conversations/latest
    POST   /chat/conversations
    GET    /chat/conversations/{conversation_id}
    POST   /chat/conversations/{conversation_id}/messages  (streaming ndjson)

The streaming endpoint forwards Ollama tokens to the browser as newline-
delimited JSON frames and detects client disconnect via
`Request.is_disconnected()` so cancellation can save the partial reply.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.ollama_client import OllamaUnreachableError, stream_chat

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── Pydantic schemas ─────────────────────────────────────────────────────


class ChatMessageCreate(BaseModel):
    content: str = Field(..., max_length=8192)

    @field_validator("content")
    @classmethod
    def not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content must not be empty or whitespace-only")
        return stripped


class ChatMessageRead(BaseModel):
    id: int
    role: str
    content: str
    created_at: str
    finished_at: str | None
    cancelled: bool


class ChatConversationRead(BaseModel):
    id: int
    created_at: str
    updated_at: str
    title: str | None
    messages: list[ChatMessageRead]


def _msg_to_read(m: Message) -> ChatMessageRead:
    return ChatMessageRead(
        id=m.id,
        role=m.role,
        content=m.content,
        created_at=m.created_at.isoformat() + "Z",
        finished_at=(m.finished_at.isoformat() + "Z") if m.finished_at else None,
        cancelled=m.cancelled,
    )


def _conv_to_read(c: Conversation) -> ChatConversationRead:
    return ChatConversationRead(
        id=c.id,
        created_at=c.created_at.isoformat() + "Z",
        updated_at=c.updated_at.isoformat() + "Z",
        title=c.title,
        messages=[_msg_to_read(m) for m in c.messages],
    )


# ── CRUD endpoints ───────────────────────────────────────────────────────


@router.get("/conversations/latest")
async def get_latest_conversation(db: DbDep, response: Response):
    """Return the most recently updated conversation, or 204 if none exist."""
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(1)
    )
    conv = result.scalars().first()
    if conv is None:
        response.status_code = 204
        return None
    return _conv_to_read(conv)


@router.post("/conversations", status_code=201, response_model=ChatConversationRead)
async def create_conversation(db: DbDep) -> ChatConversationRead:
    """Create a new, empty conversation (the 'New chat' button)."""
    conv = Conversation()
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    # Build the response directly — new conversations have no messages, so
    # there's no need to trigger a lazy-load on the relationship.
    return ChatConversationRead(
        id=conv.id,
        created_at=conv.created_at.isoformat() + "Z",
        updated_at=conv.updated_at.isoformat() + "Z",
        title=conv.title,
        messages=[],
    )


@router.get("/conversations/{conversation_id}", response_model=ChatConversationRead)
async def get_conversation(conversation_id: int, db: DbDep) -> ChatConversationRead:
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conv = result.scalars().first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_to_read(conv)


# ── Streaming message endpoint ───────────────────────────────────────────


def _frame(obj: dict) -> bytes:
    """Encode a single ndjson frame (JSON line + \\n)."""
    return (json.dumps(obj) + "\n").encode("utf-8")


async def _build_messages_for_llm(
    db: AsyncSession,
    conversation: Conversation,
    new_user_content: str,
) -> list[dict]:
    """Build the Ollama /api/chat messages list.

    In US1 this uses a static system prompt (no grounding). US2 replaces this
    with `prompt_assembler.assemble_chat_messages` which pulls live network
    state from F4.2/F4.3 tables.
    """
    # Late import so US2 can add the module without touching this file.
    try:
        from app.services.prompt_assembler import assemble_chat_messages

        return await assemble_chat_messages(db, conversation.id, new_user_content)
    except ImportError:
        # US1 fallback: static system prompt with full prior exchange.
        system_prompt = (
            "You are the Camelot network advisor, a conversational assistant "
            "for a single home administrator managing a small home network. "
            "Answer questions clearly and concisely. If you are not sure, say so."
        )
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for m in conversation.messages:
            messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": new_user_content})
        return messages


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: int,
    body: ChatMessageCreate,
    request: Request,
    db: DbDep,
):
    """Post a user message and stream the advisor reply as ndjson frames."""
    # Load the conversation + prior messages in one query.
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conv = result.scalars().first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Persist the user's turn first so the assembler can see it via DB if
    # needed. Also insert the assistant shell with empty content so we have
    # a stable id to return in the `start` frame.
    user_msg = Message(conversation_id=conv.id, role="user", content=body.content)
    db.add(user_msg)
    assistant_msg = Message(
        conversation_id=conv.id, role="assistant", content=""
    )
    db.add(assistant_msg)
    # Bump updated_at explicitly (onupdate only fires on UPDATE, not INSERT).
    conv.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)
    await db.refresh(conv, attribute_names=["messages"])

    assistant_id = assistant_msg.id

    # Assemble the messages list to send to Ollama. Exclude the empty
    # assistant shell we just inserted (it's the placeholder for this turn).
    messages_for_llm = await _build_messages_for_llm(
        db, conv, body.content
    )

    async def stream_frames() -> AsyncIterator[bytes]:
        start_wall = time.monotonic()
        buffer_parts: list[str] = []
        cancelled = False
        error_message: str | None = None
        last_disconnect_check = 0.0
        eval_count_hint = 0

        yield _frame({"type": "start", "message_id": assistant_id})

        try:
            async for chunk in stream_chat(messages_for_llm):
                buffer_parts.append(chunk)
                eval_count_hint += 1
                yield _frame({"type": "token", "content": chunk})

                # Poll for client disconnect at most ~10x/second.
                now = time.monotonic()
                if now - last_disconnect_check > 0.1:
                    last_disconnect_check = now
                    if await request.is_disconnected():
                        cancelled = True
                        break
        except OllamaUnreachableError as e:
            logger.warning(
                "chat_ollama_unreachable",
                extra={"conversation_id": conv.id, "error": str(e)},
            )
            error_message = (
                "The advisor is temporarily unavailable. "
                "Please check that Ollama is running and try again."
            )
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            # Persist the final state of the assistant message in one write.
            # Use a fresh session to avoid colliding with the outer request
            # session which may already be closed in the cancel path.
            duration_ms = int((time.monotonic() - start_wall) * 1000)
            final_content = "".join(buffer_parts)
            async with async_session() as write_session:
                db_msg = await write_session.get(Message, assistant_id)
                if db_msg is not None:
                    db_msg.content = final_content
                    db_msg.finished_at = datetime.utcnow()
                    db_msg.cancelled = cancelled
                    # Bump conversation.updated_at on completion too.
                    db_conv = await write_session.get(Conversation, conv.id)
                    if db_conv is not None:
                        db_conv.updated_at = datetime.utcnow()
                    await write_session.commit()

            logger.info(
                "chat_turn",
                extra={
                    "conversation_id": conv.id,
                    "message_id": assistant_id,
                    "duration_ms": duration_ms,
                    "content_chars": len(final_content),
                    "eval_count_hint": eval_count_hint,
                    "cancelled": cancelled,
                    "ollama_error": error_message,
                },
            )

        if error_message is not None:
            yield _frame(
                {
                    "type": "error",
                    "message_id": assistant_id,
                    "message": error_message,
                }
            )
            return
        if not cancelled:
            yield _frame(
                {
                    "type": "done",
                    "message_id": assistant_id,
                    "duration_ms": int((time.monotonic() - start_wall) * 1000),
                    "cancelled": False,
                }
            )
        # Cancelled path: disconnect is the terminal signal; no final frame.

    return StreamingResponse(stream_frames(), media_type="application/x-ndjson")


# ── Suggest notes ───────────────────────────────────────────────────────


@router.post("/conversations/{conversation_id}/suggest-notes")
async def suggest_notes(conversation_id: int, db: DbDep):
    """Extract note suggestions from conversation via LLM (FR-014)."""
    from app.services.note_suggester import generate_suggestions

    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conv = result.scalars().first()
    if conv is None:
        raise HTTPException(404, "Conversation not found")

    messages = [
        {"role": m.role, "content": m.content}
        for m in conv.messages
        if m.content
    ]

    try:
        suggestions = await generate_suggestions(db, messages)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "suggest_notes_failed", extra={"error": str(e)}
        )
        return {"suggestions": [], "error": "LLM service unavailable"}

    return {"suggestions": suggestions}
