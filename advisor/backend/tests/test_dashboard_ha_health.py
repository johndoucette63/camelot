"""Tests for dashboard summary `integrations.home_assistant` block (T037b).

Covers FR-025 — HA integration health must be surfaced on the dashboard
summary endpoint so the top-nav status pill can render a single source of
truth rather than digging through logs.

Each test sets the singleton ``home_assistant_connections`` row into one
of the five status classes and asserts the shape of the returned block:

    integrations:
      home_assistant:
        configured: bool
        status: "ok" | "auth_failure" | "unreachable" | "unexpected_payload" | "not_configured"
        last_success_at: iso8601 | null
        last_error: str | null

* not_configured → configured=false, status="not_configured", both times null.
* ok             → configured=true, status="ok", last_success_at set,
                   last_error null.
* auth_failure   → configured=true, status="auth_failure", last_error set.
* unreachable    → configured=true, status="unreachable", last_error set.
* unexpected_payload → configured=true, status="unexpected_payload".
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.home_assistant_connection import HomeAssistantConnection
from app.routers.dashboard import get_db
from app.security import encrypt_token

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    app.state.hosts_unreachable = set()

    yield session_factory

    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed_connection(
    session_factory,
    *,
    configured: bool = True,
    last_error: str | None = None,
    last_success_at: datetime | None = None,
):
    async with session_factory() as session:
        conn = HomeAssistantConnection(id=1)
        if configured:
            conn.base_url = "http://homeassistant.local:8123"
            conn.token_ciphertext = encrypt_token("llat_x")
        if last_success_at is not None:
            conn.last_success_at = last_success_at
        if last_error:
            conn.last_error = last_error
            conn.last_error_at = _utcnow()
        session.add(conn)
        await session.commit()


def _ha_block(payload: dict) -> dict:
    """Pull the ``integrations.home_assistant`` block from the response."""
    integrations = payload.get("integrations") or {}
    return integrations.get("home_assistant") or {}


async def _get_summary() -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/summary")
    assert resp.status_code == 200
    return resp.json()


# ── (a) not_configured ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_not_configured(db_and_override):
    await _seed_connection(db_and_override, configured=False)

    data = await _get_summary()
    ha = _ha_block(data)

    assert ha["configured"] is False
    assert ha["status"] == "not_configured"
    assert ha["last_success_at"] is None
    assert ha["last_error"] is None


# ── (b) ok ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_ok(db_and_override):
    await _seed_connection(
        db_and_override,
        configured=True,
        last_success_at=_utcnow(),
    )

    data = await _get_summary()
    ha = _ha_block(data)

    assert ha["configured"] is True
    assert ha["status"] == "ok"
    assert ha["last_success_at"] is not None
    assert ha["last_error"] is None


# ── (c) auth_failure ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_auth_failure(db_and_override):
    await _seed_connection(
        db_and_override,
        configured=True,
        last_error="auth_failure",
    )

    data = await _get_summary()
    ha = _ha_block(data)

    assert ha["configured"] is True
    assert ha["status"] == "auth_failure"
    assert ha["last_error"] == "auth_failure"


# ── (d) unreachable ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_unreachable(db_and_override):
    await _seed_connection(
        db_and_override,
        configured=True,
        last_error="unreachable",
    )

    data = await _get_summary()
    ha = _ha_block(data)

    assert ha["configured"] is True
    assert ha["status"] == "unreachable"
    assert ha["last_error"] == "unreachable"


# ── (e) unexpected_payload ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_unexpected_payload(db_and_override):
    await _seed_connection(
        db_and_override,
        configured=True,
        last_error="unexpected_payload",
    )

    data = await _get_summary()
    ha = _ha_block(data)

    assert ha["configured"] is True
    assert ha["status"] == "unexpected_payload"
    assert ha["last_error"] == "unexpected_payload"
