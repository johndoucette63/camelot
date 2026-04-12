"""Tests for note_suggester service — T031."""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.rejected_suggestion import RejectedSuggestion

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _fake_stream(*chunks):
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_valid_json_extraction(db):
    from app.services.note_suggester import generate_suggestions

    suggestions_json = json.dumps([
        {"target_type": "device", "target_id": 1, "target_label": "NAS", "body": "NAS scrub every Sunday"},
    ])

    with patch("app.services.note_suggester.stream_chat", return_value=_fake_stream(suggestions_json)):
        result = await generate_suggestions(db, [
            {"role": "user", "content": "The NAS scrub happens Sunday nights"},
        ])

    assert len(result) == 1
    assert result[0]["body"] == "NAS scrub every Sunday"
    assert result[0]["target_type"] == "device"


@pytest.mark.asyncio
async def test_empty_conversation_returns_empty(db):
    from app.services.note_suggester import generate_suggestions

    result = await generate_suggestions(db, [])
    assert result == []


@pytest.mark.asyncio
async def test_ollama_unreachable_returns_empty(db):
    from app.services.note_suggester import generate_suggestions
    from app.services.ollama_client import OllamaUnreachableError

    async def _failing_stream(*args, **kwargs):
        raise OllamaUnreachableError("Connection refused")
        yield  # make it an async generator

    with patch("app.services.note_suggester.stream_chat", return_value=_failing_stream()):
        result = await generate_suggestions(db, [
            {"role": "user", "content": "Some conversation"},
        ])

    assert result == []


@pytest.mark.asyncio
async def test_rejected_hashes_filtered(db):
    from app.services.note_suggester import generate_suggestions, _hash_body

    # Pre-reject a suggestion
    body_text = "NAS scrub every Sunday"
    rejection = RejectedSuggestion(content_hash=_hash_body(body_text))
    db.add(rejection)
    await db.commit()

    suggestions_json = json.dumps([
        {"target_type": "device", "target_id": 1, "target_label": "NAS", "body": body_text},
        {"target_type": "playbook", "body": "VPN rotates monthly"},
    ])

    with patch("app.services.note_suggester.stream_chat", return_value=_fake_stream(suggestions_json)):
        result = await generate_suggestions(db, [
            {"role": "user", "content": "conversation"},
        ])

    # Only the non-rejected suggestion should remain
    assert len(result) == 1
    assert result[0]["body"] == "VPN rotates monthly"


@pytest.mark.asyncio
async def test_bad_json_returns_empty(db):
    from app.services.note_suggester import generate_suggestions

    with patch("app.services.note_suggester.stream_chat", return_value=_fake_stream("not valid json")):
        result = await generate_suggestions(db, [
            {"role": "user", "content": "conversation"},
        ])

    assert result == []
