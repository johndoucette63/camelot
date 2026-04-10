"""Tests for the chat router: conversation CRUD + streaming endpoint.

The Ollama HTTP boundary is the only external system mocked. Database goes
through the existing SQLite aiosqlite in-memory fixture pattern used by
test_events_api.py and test_dashboard_api.py.
"""

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.conversation import Conversation
from app.models.message import Message
from app.routers.chat import get_db
from app.services import ollama_client as ollama_module

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_and_override():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Also override the chat router's `async_session` usage inside the
    # streaming finalization block so it uses the test engine.
    from app.routers import chat as chat_module

    original_async_session = chat_module.async_session
    chat_module.async_session = session_factory

    async with session_factory() as session:
        yield session

    chat_module.async_session = original_async_session
    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _fake_stream(tokens: list[str]):
    async def _stream(messages, model=None):  # noqa: ARG001
        for t in tokens:
            yield t

    return _stream


def _failing_stream(exc: Exception):
    async def _stream(messages, model=None):  # noqa: ARG001
        raise exc
        yield  # pragma: no cover

    return _stream


async def _parse_ndjson(body: bytes) -> list[dict]:
    import json

    frames = []
    for line in body.decode("utf-8").splitlines():
        line = line.strip()
        if line:
            frames.append(json.loads(line))
    return frames


@pytest.mark.asyncio
async def test_get_latest_returns_204_when_no_conversations(db_and_override):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/chat/conversations/latest")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_post_creates_empty_conversation(db_and_override):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/chat/conversations")
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] > 0
    assert data["messages"] == []
    assert data["title"] is None


@pytest.mark.asyncio
async def test_get_by_id_returns_404_for_missing(db_and_override):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/chat/conversations/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_latest_returns_most_recently_updated(db_and_override):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = (await client.post("/chat/conversations")).json()
        second = (await client.post("/chat/conversations")).json()
        latest = (await client.get("/chat/conversations/latest")).json()
    assert latest["id"] == second["id"]
    assert latest["id"] != first["id"]


@pytest.mark.asyncio
async def test_post_message_validates_empty_content(db_and_override):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conv = (await client.post("/chat/conversations")).json()
        resp = await client.post(
            f"/chat/conversations/{conv['id']}/messages",
            json={"content": "   "},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_message_404_for_missing_conversation(
    db_and_override, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.chat.stream_chat", _fake_stream(["hello"])
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/chat/conversations/9999/messages",
            json={"content": "hello"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_message_streams_ndjson_frames_in_expected_order(
    db_and_override, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.chat.stream_chat",
        _fake_stream(["Hello", " ", "world"]),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conv = (await client.post("/chat/conversations")).json()
        resp = await client.post(
            f"/chat/conversations/{conv['id']}/messages",
            json={"content": "Hi there"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    frames = await _parse_ndjson(resp.content)
    types = [f["type"] for f in frames]
    assert types[0] == "start"
    assert types[-1] == "done"
    token_frames = [f for f in frames if f["type"] == "token"]
    assert [f["content"] for f in token_frames] == ["Hello", " ", "world"]
    assert frames[-1]["cancelled"] is False


@pytest.mark.asyncio
async def test_post_message_persists_user_and_assistant_rows(
    db_and_override, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.chat.stream_chat", _fake_stream(["ack"])
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conv = (await client.post("/chat/conversations")).json()
        resp = await client.post(
            f"/chat/conversations/{conv['id']}/messages",
            json={"content": "ping"},
        )
        assert resp.status_code == 200
        # Drain the stream so the finalizer runs.
        _ = resp.content

        fetched = (await client.get(f"/chat/conversations/{conv['id']}")).json()

    msgs = fetched["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "ping"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "ack"
    assert msgs[1]["finished_at"] is not None
    assert msgs[1]["cancelled"] is False


@pytest.mark.asyncio
async def test_post_message_returns_error_frame_when_ollama_unreachable(
    db_and_override, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.chat.stream_chat",
        _failing_stream(
            ollama_module.OllamaUnreachableError("Could not reach Ollama")
        ),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conv = (await client.post("/chat/conversations")).json()
        resp = await client.post(
            f"/chat/conversations/{conv['id']}/messages",
            json={"content": "ping"},
        )
    assert resp.status_code == 200
    frames = await _parse_ndjson(resp.content)
    types = [f["type"] for f in frames]
    assert types[0] == "start"
    assert "error" in types
    err = next(f for f in frames if f["type"] == "error")
    assert "unavailable" in err["message"].lower()
    # The `done` frame must NOT be emitted after an error.
    assert "done" not in types


@pytest.mark.asyncio
async def test_post_message_includes_prior_exchange_in_prompt(
    db_and_override, monkeypatch
):
    """Multi-turn memory: the second message's Ollama call must see the
    first turn's user+assistant messages."""
    captured_message_lists: list[list[dict]] = []

    async def capturing_stream(messages, model=None):  # noqa: ARG001
        captured_message_lists.append(messages)
        yield "ok"

    monkeypatch.setattr("app.routers.chat.stream_chat", capturing_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conv = (await client.post("/chat/conversations")).json()
        await client.post(
            f"/chat/conversations/{conv['id']}/messages",
            json={"content": "first question"},
        )
        await client.post(
            f"/chat/conversations/{conv['id']}/messages",
            json={"content": "second question"},
        )

    assert len(captured_message_lists) == 2
    second_call = captured_message_lists[1]
    roles = [m["role"] for m in second_call]
    assert roles[0] == "system"
    # system + prior user + prior assistant + new user
    assert roles[-4:] == ["system", "user", "assistant", "user"] or (
        roles.count("user") >= 2 and roles.count("assistant") >= 1
    )
    assert second_call[-1]["content"] == "second question"
