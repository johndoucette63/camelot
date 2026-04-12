"""Notes CRUD — per-device, per-service, and playbook entries."""

import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.device import Device
from app.models.note import Note
from app.models.rejected_suggestion import RejectedSuggestion
from app.models.service_definition import ServiceDefinition
from app.schemas.note import (
    NoteCreate,
    NoteListResponse,
    NoteResponse,
    NoteUpdate,
    RejectedSuggestionCreate,
    RejectedSuggestionResponse,
    TagListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

PINNED_CAP_PER_CATEGORY = 20


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


def _note_to_response(note: Note) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        target_type=note.target_type,
        target_id=note.target_id,
        title=note.title,
        body=note.body,
        pinned=note.pinned,
        tags=note.tags or [],
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


# ── List notes ──────────────────────────────────────────────────────────


@router.get("", response_model=NoteListResponse)
async def list_notes(
    db: DbDep,
    target_type: str = Query(..., pattern="^(device|service|playbook)$"),
    target_id: int | None = None,
    tag: str | None = None,
) -> NoteListResponse:
    stmt = (
        select(Note)
        .where(Note.target_type == target_type)
        .order_by(Note.updated_at.desc())
    )

    if target_type in ("device", "service") and target_id is not None:
        stmt = stmt.where(Note.target_id == target_id)

    if tag and target_type == "playbook":
        # Filter playbook entries containing the given tag in their JSON array
        stmt = stmt.where(Note.tags.op("@>")(f'["{tag}"]'))

    result = await db.execute(stmt)
    notes = result.scalars().all()
    return NoteListResponse(
        notes=[_note_to_response(n) for n in notes],
        total=len(notes),
    )


# ── Create note ─────────────────────────────────────────────────────────


@router.post("", response_model=NoteResponse, status_code=201)
async def create_note(body: NoteCreate, db: DbDep) -> NoteResponse:
    # Validate target exists for device/service notes
    if body.target_type == "device":
        if body.target_id is None:
            raise HTTPException(400, "target_id is required for device notes")
        exists = await db.execute(
            select(Device.id).where(Device.id == body.target_id)
        )
        if not exists.scalar_one_or_none():
            raise HTTPException(404, f"Device {body.target_id} not found")

    elif body.target_type == "service":
        if body.target_id is None:
            raise HTTPException(400, "target_id is required for service notes")
        exists = await db.execute(
            select(ServiceDefinition.id).where(
                ServiceDefinition.id == body.target_id
            )
        )
        if not exists.scalar_one_or_none():
            raise HTTPException(404, f"Service {body.target_id} not found")

    elif body.target_type == "playbook":
        if body.target_id is not None:
            raise HTTPException(400, "target_id must be null for playbook entries")

    # Enforce pinned cap
    if body.pinned:
        await _check_pinned_cap(db, body.target_type, body.target_id)

    note = Note(
        target_type=body.target_type,
        target_id=body.target_id,
        title=body.title,
        body=body.body,
        pinned=body.pinned,
        tags=body.tags,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    logger.info("note_created", extra={"note_id": note.id, "target_type": note.target_type})
    return _note_to_response(note)


# ── Update note ─────────────────────────────────────────────────────────


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(note_id: int, body: NoteUpdate, db: DbDep) -> NoteResponse:
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(404, "Note not found")

    if body.pinned is True and not note.pinned:
        await _check_pinned_cap(db, note.target_type, note.target_id)

    if body.title is not None:
        note.title = body.title
    if body.body is not None:
        note.body = body.body
    if body.pinned is not None:
        note.pinned = body.pinned
    if body.tags is not None:
        note.tags = body.tags

    await db.commit()
    await db.refresh(note)
    return _note_to_response(note)


# ── Delete note ─────────────────────────────────────────────────────────


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: int, db: DbDep) -> None:
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(404, "Note not found")
    await db.delete(note)
    await db.commit()


# ── Tags autocomplete ───────────────────────────────────────────────────


@router.get("/tags", response_model=TagListResponse)
async def list_tags(db: DbDep) -> TagListResponse:
    # Use jsonb_array_elements_text to extract distinct tags from playbook notes
    result = await db.execute(
        text(
            "SELECT DISTINCT tag FROM notes, "
            "jsonb_array_elements_text(tags::jsonb) AS tag "
            "WHERE target_type = 'playbook' "
            "ORDER BY tag"
        )
    )
    tags = [row[0] for row in result.all()]
    return TagListResponse(tags=tags)


# ── Rejected suggestions ───────────────────────────────────────────────


@router.post("/rejected-suggestions", response_model=RejectedSuggestionResponse)
async def reject_suggestion(
    body: RejectedSuggestionCreate, db: DbDep
) -> RejectedSuggestionResponse:
    content_hash = _hash_suggestion(body.body)

    # Idempotent: check if already rejected
    result = await db.execute(
        select(RejectedSuggestion).where(
            RejectedSuggestion.content_hash == content_hash
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return RejectedSuggestionResponse(
            id=existing.id,
            content_hash=existing.content_hash,
            created_at=existing.created_at,
        )

    rejection = RejectedSuggestion(
        content_hash=content_hash,
        conversation_id=body.conversation_id,
    )
    db.add(rejection)
    await db.commit()
    await db.refresh(rejection)
    return RejectedSuggestionResponse(
        id=rejection.id,
        content_hash=rejection.content_hash,
        created_at=rejection.created_at,
    )


# ── Cascade delete utility ──────────────────────────────────────────────


async def cascade_delete_notes(
    db: AsyncSession, target_type: str, target_id: int
) -> int:
    """Delete all notes for the given target. Returns count of deleted rows."""
    result = await db.execute(
        delete(Note).where(
            Note.target_type == target_type,
            Note.target_id == target_id,
        )
    )
    return result.rowcount


# ── Helpers ─────────────────────────────────────────────────────────────


async def _check_pinned_cap(
    db: AsyncSession, target_type: str, target_id: int | None
) -> None:
    stmt = select(func.count()).where(
        Note.target_type == target_type,
        Note.pinned.is_(True),
    )
    if target_id is not None:
        stmt = stmt.where(Note.target_id == target_id)
    else:
        stmt = stmt.where(Note.target_id.is_(None))

    result = await db.execute(stmt)
    count = result.scalar() or 0
    if count >= PINNED_CAP_PER_CATEGORY:
        raise HTTPException(
            409,
            f"Maximum {PINNED_CAP_PER_CATEGORY} pinned notes per category reached",
        )


def _hash_suggestion(body: str) -> str:
    """Normalise and SHA-256 hash a suggestion body for dedup."""
    normalised = " ".join(body.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()
