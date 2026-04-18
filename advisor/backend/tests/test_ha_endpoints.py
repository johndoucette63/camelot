"""Tests for GET /ha/entities (feature 016, T035).

Exercises contracts/home-assistant-api.md §2:

* Snapshot rows are returned with the correct shape.
* ``domain`` query param filters by HA domain.
* ``search`` query param does a substring match against friendly_name.
* When the singleton connection is in an error state (``last_error`` set)
  the response carries ``stale=true`` AND still returns the last-known
  snapshot (FR-008 persistence).
* When no connection is configured AND no snapshots exist, the response
  returns ``connection_status="not_configured"`` and ``entities=[]``.
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
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.thread_border_router import ThreadBorderRouter
from app.models.thread_device import ThreadDevice
from app.routers import home_assistant as ha_router
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

    # The home_assistant router, like other routers, uses the module-level
    # ``async_session``. Swap it to our in-memory factory.
    original = ha_router.async_session
    ha_router.async_session = session_factory

    yield session_factory

    ha_router.async_session = original
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _seed_snapshot(session, **overrides):
    now = _utcnow()
    fields = {
        "entity_id": overrides.get("entity_id", "switch.lamp"),
        "ha_device_id": overrides.get("ha_device_id", "dev-1"),
        "domain": overrides.get("domain", "switch"),
        "friendly_name": overrides.get("friendly_name", "Lamp"),
        "state": overrides.get("state", "on"),
        "last_changed": overrides.get("last_changed", now),
        "attributes": overrides.get("attributes", {}),
        "polled_at": overrides.get("polled_at", now),
    }
    session.add(HAEntitySnapshot(**fields))


async def _configure_connection(
    session_factory,
    *,
    configured: bool = True,
    last_error: str | None = None,
):
    async with session_factory() as session:
        conn = HomeAssistantConnection(id=1)
        if configured:
            conn.base_url = "http://homeassistant.local:8123"
            conn.token_ciphertext = encrypt_token("llat_test")
            conn.last_success_at = _utcnow()
        if last_error:
            conn.last_error = last_error
            conn.last_error_at = _utcnow()
        session.add(conn)
        await session.commit()


# ── (a) GET returns all snapshots ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entities_returns_all(db_and_override):
    session_factory = db_and_override
    await _configure_connection(session_factory)

    async with session_factory() as session:
        _seed_snapshot(session, entity_id="switch.lamp", domain="switch",
                       friendly_name="Lamp", ha_device_id="dev-1")
        _seed_snapshot(session, entity_id="switch.fan", domain="switch",
                       friendly_name="Fan", ha_device_id="dev-2")
        _seed_snapshot(
            session,
            entity_id="binary_sensor.front_door",
            domain="binary_sensor",
            friendly_name="Front Door",
            ha_device_id="dev-3",
        )
        _seed_snapshot(
            session,
            entity_id="binary_sensor.back_door",
            domain="binary_sensor",
            friendly_name="Back Door",
            ha_device_id="dev-4",
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ha/entities")

    assert resp.status_code == 200
    body = resp.json()
    assert body["connection_status"] == "ok"
    assert body["stale"] is False
    assert len(body["entities"]) == 4


# ── (b) domain filter ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entities_filters_by_domain(db_and_override):
    session_factory = db_and_override
    await _configure_connection(session_factory)

    async with session_factory() as session:
        _seed_snapshot(session, entity_id="switch.lamp", domain="switch",
                       friendly_name="Lamp", ha_device_id="dev-1")
        _seed_snapshot(session, entity_id="switch.fan", domain="switch",
                       friendly_name="Fan", ha_device_id="dev-2")
        _seed_snapshot(
            session,
            entity_id="binary_sensor.front_door",
            domain="binary_sensor",
            friendly_name="Front Door",
            ha_device_id="dev-3",
        )
        _seed_snapshot(
            session,
            entity_id="binary_sensor.back_door",
            domain="binary_sensor",
            friendly_name="Back Door",
            ha_device_id="dev-4",
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ha/entities", params={"domain": "binary_sensor"})

    assert resp.status_code == 200
    body = resp.json()
    domains = {e["domain"] for e in body["entities"]}
    assert domains == {"binary_sensor"}
    assert len(body["entities"]) == 2


# ── (c) search filter on friendly_name ─────────────────────────────────


@pytest.mark.asyncio
async def test_get_entities_search_by_friendly_name(db_and_override):
    session_factory = db_and_override
    await _configure_connection(session_factory)

    async with session_factory() as session:
        _seed_snapshot(session, entity_id="switch.lamp", domain="switch",
                       friendly_name="Lamp", ha_device_id="dev-1")
        _seed_snapshot(
            session,
            entity_id="binary_sensor.front_door",
            domain="binary_sensor",
            friendly_name="Front Door",
            ha_device_id="dev-3",
        )
        _seed_snapshot(
            session,
            entity_id="binary_sensor.back_door",
            domain="binary_sensor",
            friendly_name="Back Door",
            ha_device_id="dev-4",
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ha/entities", params={"search": "Front"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["entities"]) == 1
    assert body["entities"][0]["friendly_name"] == "Front Door"


# ── (d) stale flag when connection is in error, entities still returned ─


@pytest.mark.asyncio
async def test_get_entities_stale_but_persisted_on_error(db_and_override):
    session_factory = db_and_override
    await _configure_connection(session_factory, last_error="unreachable")

    async with session_factory() as session:
        _seed_snapshot(
            session,
            entity_id="binary_sensor.front_door",
            domain="binary_sensor",
            friendly_name="Front Door",
            ha_device_id="dev-3",
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ha/entities")

    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    # FR-008: last-known snapshot remains visible even when HA is unreachable.
    assert len(body["entities"]) == 1


# ── (e) unconfigured + no snapshots → empty response ───────────────────


@pytest.mark.asyncio
async def test_get_entities_unconfigured_empty(db_and_override):
    session_factory = db_and_override
    # Seed the singleton row unconfigured (base_url IS NULL).
    async with session_factory() as session:
        session.add(HomeAssistantConnection(id=1))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ha/entities")

    assert resp.status_code == 200
    body = resp.json()
    assert body["connection_status"] == "not_configured"
    assert body["entities"] == []
    assert body["stale"] is False


# ── (f) GET /ha/thread happy path ──────────────────────────────────────


def _seed_router(session, **overrides):
    now = _utcnow()
    fields = {
        "ha_device_id": overrides.get("ha_device_id", "br-1"),
        "friendly_name": overrides.get("friendly_name", "Kitchen Hub"),
        "model": overrides.get("model"),
        "online": overrides.get("online", True),
        "attached_device_count": overrides.get("attached_device_count", 0),
        "last_refreshed_at": overrides.get("last_refreshed_at", now),
    }
    session.add(ThreadBorderRouter(**fields))


def _seed_thread_device(session, **overrides):
    now = _utcnow()
    fields = {
        "ha_device_id": overrides.get("ha_device_id", "dev-42"),
        "friendly_name": overrides.get("friendly_name", "Hallway Motion"),
        "parent_border_router_id": overrides.get("parent_border_router_id", "br-1"),
        "online": overrides.get("online", True),
        "last_seen_parent_id": overrides.get("last_seen_parent_id"),
        "last_refreshed_at": overrides.get("last_refreshed_at", now),
    }
    session.add(ThreadDevice(**fields))


@pytest.mark.asyncio
async def test_get_thread_returns_populated_payload(db_and_override):
    session_factory = db_and_override
    await _configure_connection(session_factory)

    async with session_factory() as session:
        _seed_router(
            session,
            ha_device_id="br-1",
            friendly_name="HomePod mini — Kitchen",
            model="HomePod mini",
            online=True,
            attached_device_count=1,
        )
        await session.commit()
        _seed_thread_device(
            session,
            ha_device_id="dev-42",
            friendly_name="Hallway Motion",
            parent_border_router_id="br-1",
            last_seen_parent_id="br-1",
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/ha/thread")

    assert resp.status_code == 200
    body = resp.json()
    assert body["connection_status"] == "ok"
    assert body["empty_reason"] is None
    assert body["orphaned_device_count"] == 0
    assert len(body["border_routers"]) == 1
    assert body["border_routers"][0]["friendly_name"] == "HomePod mini — Kitchen"
    assert body["border_routers"][0]["attached_device_count"] == 1
    assert len(body["devices"]) == 1
    assert body["devices"][0]["parent_border_router_id"] == "br-1"
    assert body["devices"][0]["last_seen_parent_id"] == "br-1"
    # polled_at comes from the router's last_refreshed_at.
    assert body["polled_at"] is not None


# ── (g) GET /ha/thread orphan accounting ───────────────────────────────


@pytest.mark.asyncio
async def test_get_thread_counts_orphans(db_and_override):
    session_factory = db_and_override
    await _configure_connection(session_factory)

    async with session_factory() as session:
        _seed_router(session, ha_device_id="br-1", friendly_name="Router 1")
        await session.commit()
        _seed_thread_device(
            session,
            ha_device_id="dev-attached",
            friendly_name="Attached",
            parent_border_router_id="br-1",
            last_seen_parent_id="br-1",
        )
        _seed_thread_device(
            session,
            ha_device_id="dev-orphan",
            friendly_name="Orphan",
            parent_border_router_id=None,
            last_seen_parent_id="br-1",
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/ha/thread")

    assert resp.status_code == 200
    body = resp.json()
    assert body["orphaned_device_count"] == 1
    assert len(body["devices"]) == 2


# ── (h) GET /ha/thread empty-state ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_thread_empty_state_when_no_data_and_ok(db_and_override):
    session_factory = db_and_override
    await _configure_connection(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/ha/thread")

    assert resp.status_code == 200
    body = resp.json()
    assert body["connection_status"] == "ok"
    assert body["empty_reason"] == "no_thread_integration_data"
    assert body["border_routers"] == []
    assert body["devices"] == []
    assert body["orphaned_device_count"] == 0


# ── (i) GET /ha/thread not-configured ──────────────────────────────────


@pytest.mark.asyncio
async def test_get_thread_not_configured(db_and_override):
    session_factory = db_and_override
    # Seed a singleton row with base_url NULL.
    async with session_factory() as session:
        session.add(HomeAssistantConnection(id=1))
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/ha/thread")

    assert resp.status_code == 200
    body = resp.json()
    assert body["connection_status"] == "not_configured"
    # empty_reason only set when status is "ok"; for not_configured it's None.
    assert body["empty_reason"] is None
    assert body["border_routers"] == []
    assert body["devices"] == []
