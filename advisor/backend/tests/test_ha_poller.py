"""Tests for app.services.ha_poller (feature 016, T032).

Drives the real ``run_cycle()`` against an in-memory SQLite DB with the
HA REST client mocked at the module boundary. Each test:

1. Seeds the singleton ``home_assistant_connections`` row.
2. Patches ``ha_client.states`` to return a synthetic entity list (or to raise).
3. Runs ONE cycle (not the outer while-loop).
4. Asserts the post-cycle state of ``ha_entity_snapshots`` + the connection row.

Scenarios covered:

* Filtering — 5-6 allowlisted entities land in the snapshot table while
  ~4 off-allowlist entities are dropped, and last_success_at advances.
* Error classification — ``HAAuthError`` from the client records
  ``last_error='auth_failure'`` and leaves the snapshot table untouched.
* Disappearance — an entity present in cycle 1 but absent from cycle 2 is
  deleted from the snapshot table; entities still present remain.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.thread_border_router import ThreadBorderRouter
from app.models.thread_device import ThreadDevice
from app.security import encrypt_token
from app.services import ha_client, ha_inventory_merge, ha_poller
from app.services.ha_client import HAAuthError
from app.services.ha_poller import run_cycle

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── fixtures ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def poller_env(monkeypatch):
    """Fresh in-memory DB + HA connection singleton, wired into ha_poller.

    Patches ha_poller.async_session to the test factory and replaces the
    inventory-merge call with an AsyncMock so poller tests can focus on
    snapshot behaviour without pulling in the merge function's surface.
    """
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

    # Seed the singleton connection row — id=1, configured.
    async with session_factory() as session:
        conn_row = HomeAssistantConnection(
            id=1,
            base_url="http://homeassistant.local:8123",
            token_ciphertext=encrypt_token("llat_test_token_ABCD"),
        )
        session.add(conn_row)
        await session.commit()

    monkeypatch.setattr(ha_poller, "async_session", session_factory)

    # Isolate the poller from the inventory-merge surface so we only exercise
    # snapshot/error behaviour here. The merge has its own test file (T033).
    monkeypatch.setattr(
        ha_inventory_merge,
        "merge_ha_devices",
        AsyncMock(return_value=None),
    )

    # Default: HA has no Thread integration (returns None). Individual tests
    # that care about the Thread refresh override this patch.
    monkeypatch.setattr(
        ha_client,
        "thread_status",
        AsyncMock(return_value=None),
    )

    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _entity(
    entity_id: str,
    *,
    state: str = "off",
    device_id: str = "dev-1",
    friendly_name: str | None = None,
    device_class: str | None = None,
    integration: str | None = None,
    mac: str | None = None,
) -> dict:
    """Synthetic HA ``/api/states`` entry."""
    attrs: dict = {"device_id": device_id}
    if friendly_name:
        attrs["friendly_name"] = friendly_name
    if device_class:
        attrs["device_class"] = device_class
    if integration:
        attrs["integration"] = integration
    if mac:
        attrs["mac"] = mac
    return {
        "entity_id": entity_id,
        "state": state,
        "last_changed": "2026-04-17T14:03:12+00:00",
        "attributes": attrs,
    }


# ── (a) filter + happy-path upsert ─────────────────────────────────────


@pytest.mark.asyncio
async def test_run_cycle_filters_and_upserts(poller_env, monkeypatch):
    session_factory = poller_env

    # 6 entities that should pass the R2 curated allowlist, 4 that should not.
    allowlisted = [
        _entity("device_tracker.pixel9", device_id="d1"),
        _entity("switch.lamp", device_id="d2"),
        _entity("update.ha_core", device_id="d3"),
        _entity(
            "binary_sensor.front_door",
            device_id="d4",
            device_class="connectivity",
        ),
        _entity(
            "sensor.aqara_temp",
            device_id="d5",
            device_class="temperature",
        ),
        _entity(
            "sensor.thread_border_router_1",
            device_id="d6",
            integration="thread",
        ),
    ]
    filtered_out = [
        _entity("light.living_room", device_id="d7"),
        _entity("media_player.tv", device_id="d8"),
        _entity(
            "binary_sensor.motion",
            device_id="d9",
            device_class="motion",  # not in _BINARY_SENSOR_DEVICE_CLASSES
        ),
        _entity(
            "sensor.electric_consumption",
            device_id="dA",
            device_class="energy",  # not in _SENSOR_DEVICE_CLASSES
        ),
    ]

    monkeypatch.setattr(
        ha_client,
        "states",
        AsyncMock(return_value=allowlisted + filtered_out),
    )

    stats = await run_cycle()

    assert stats["status"] == "ok"
    assert stats["entities"] == 6

    # Assert snapshot rows match the allowlisted set.
    async with session_factory() as session:
        rows = (await session.execute(select(HAEntitySnapshot))).scalars().all()
        entity_ids = {r.entity_id for r in rows}
        conn_row = await session.get(HomeAssistantConnection, 1)

    assert entity_ids == {e["entity_id"] for e in allowlisted}
    assert conn_row.last_success_at is not None
    assert conn_row.last_error is None
    assert conn_row.last_error_at is None


# ── (b) HAAuthError: snapshots untouched, error recorded ───────────────


@pytest.mark.asyncio
async def test_run_cycle_records_auth_failure(poller_env, monkeypatch):
    session_factory = poller_env

    # Seed a prior snapshot row to prove it is NOT modified on error.
    async with session_factory() as session:
        session.add(
            HAEntitySnapshot(
                entity_id="switch.lamp",
                ha_device_id="d-prior",
                domain="switch",
                friendly_name="Lamp",
                state="on",
                last_changed=_utcnow(),
                attributes={},
                polled_at=_utcnow(),
            )
        )
        await session.commit()

    monkeypatch.setattr(
        ha_client,
        "states",
        AsyncMock(side_effect=HAAuthError("HTTP 401")),
    )

    stats = await run_cycle()

    assert stats["status"] == "auth_failure"

    async with session_factory() as session:
        rows = (await session.execute(select(HAEntitySnapshot))).scalars().all()
        conn_row = await session.get(HomeAssistantConnection, 1)

    # Pre-existing rows untouched.
    assert {r.entity_id for r in rows} == {"switch.lamp"}
    # Error class persisted.
    assert conn_row.last_error == "auth_failure"
    assert conn_row.last_error_at is not None
    # last_success_at must NOT be advanced by a failing cycle.
    assert conn_row.last_success_at is None


# ── (c) entity disappears between cycles → row deleted ─────────────────


@pytest.mark.asyncio
async def test_run_cycle_deletes_disappeared_entities(poller_env, monkeypatch):
    session_factory = poller_env

    entity_a = _entity("switch.a", device_id="dA", friendly_name="A")
    entity_b = _entity("switch.b", device_id="dB", friendly_name="B")
    entity_c = _entity("switch.c", device_id="dC", friendly_name="C")

    # Cycle 1: [A, B, C]
    monkeypatch.setattr(
        ha_client,
        "states",
        AsyncMock(return_value=[entity_a, entity_b, entity_c]),
    )
    await run_cycle()

    async with session_factory() as session:
        rows = (await session.execute(select(HAEntitySnapshot))).scalars().all()
    assert {r.entity_id for r in rows} == {"switch.a", "switch.b", "switch.c"}

    # Cycle 2: [A, B] — C disappears.
    monkeypatch.setattr(
        ha_client,
        "states",
        AsyncMock(return_value=[entity_a, entity_b]),
    )
    await run_cycle()

    async with session_factory() as session:
        rows = (await session.execute(select(HAEntitySnapshot))).scalars().all()
    assert {r.entity_id for r in rows} == {"switch.a", "switch.b"}


# ── (d) Thread refresh — populated payload upserts both tables ─────────


@pytest.mark.asyncio
async def test_run_cycle_populates_thread_tables(poller_env, monkeypatch):
    """A populated thread_status payload lands in both thread_* tables."""
    session_factory = poller_env

    monkeypatch.setattr(ha_client, "states", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        ha_client,
        "thread_status",
        AsyncMock(
            return_value={
                "routers": [
                    {
                        "ha_device_id": "br-1",
                        "friendly_name": "HomePod mini — Kitchen",
                        "model": "HomePod mini",
                        "online": True,
                        "children": [
                            {
                                "ha_device_id": "dev-42",
                                "friendly_name": "Aqara Motion — Hallway",
                                "online": True,
                            }
                        ],
                    }
                ]
            }
        ),
    )

    await run_cycle()

    async with session_factory() as session:
        routers = (
            (await session.execute(select(ThreadBorderRouter))).scalars().all()
        )
        devices = (await session.execute(select(ThreadDevice))).scalars().all()

    assert {r.ha_device_id for r in routers} == {"br-1"}
    assert routers[0].friendly_name == "HomePod mini — Kitchen"
    assert routers[0].model == "HomePod mini"
    assert routers[0].online is True
    assert routers[0].attached_device_count == 1

    assert {d.ha_device_id for d in devices} == {"dev-42"}
    assert devices[0].parent_border_router_id == "br-1"
    assert devices[0].last_seen_parent_id == "br-1"
    assert devices[0].online is True


# ── (e) Thread refresh — None payload truncates both tables ────────────


@pytest.mark.asyncio
async def test_run_cycle_empties_thread_tables_when_none(poller_env, monkeypatch):
    """HA returning 404/501 (None) must leave both Thread tables empty."""
    session_factory = poller_env

    # Pre-seed rows so we prove they get removed.
    async with session_factory() as session:
        session.add(
            ThreadBorderRouter(
                ha_device_id="br-stale",
                friendly_name="Stale Router",
                model=None,
                online=True,
                attached_device_count=0,
                last_refreshed_at=_utcnow(),
            )
        )
        await session.commit()
        session.add(
            ThreadDevice(
                ha_device_id="dev-stale",
                friendly_name="Stale Device",
                parent_border_router_id="br-stale",
                online=True,
                last_seen_parent_id="br-stale",
                last_refreshed_at=_utcnow(),
            )
        )
        await session.commit()

    monkeypatch.setattr(ha_client, "states", AsyncMock(return_value=[]))
    monkeypatch.setattr(ha_client, "thread_status", AsyncMock(return_value=None))

    await run_cycle()

    async with session_factory() as session:
        routers = (
            (await session.execute(select(ThreadBorderRouter))).scalars().all()
        )
        devices = (await session.execute(select(ThreadDevice))).scalars().all()

    assert routers == []
    assert devices == []


# ── (f) last_seen_parent_id preservation across cycles ─────────────────


@pytest.mark.asyncio
async def test_thread_refresh_preserves_last_seen_parent(poller_env, monkeypatch):
    """Cycle 1 parents dev-42 on br-1; cycle 2 reports dev-42 with no parent.

    ``thread_devices.last_seen_parent_id`` must still be ``br-1`` afterwards.
    """
    session_factory = poller_env

    monkeypatch.setattr(ha_client, "states", AsyncMock(return_value=[]))

    cycle_1_payload = {
        "routers": [
            {
                "ha_device_id": "br-1",
                "friendly_name": "Router 1",
                "online": True,
                "children": [
                    {
                        "ha_device_id": "dev-42",
                        "friendly_name": "Hallway Motion",
                        "online": True,
                    }
                ],
            }
        ]
    }
    cycle_2_payload = {
        "routers": [
            {
                "ha_device_id": "br-1",
                "friendly_name": "Router 1",
                "online": True,
                # No children.
            }
        ],
        "devices": [
            {
                "ha_device_id": "dev-42",
                "friendly_name": "Hallway Motion",
                "parent_border_router_id": None,
                "online": False,
            }
        ],
    }

    monkeypatch.setattr(
        ha_client, "thread_status", AsyncMock(return_value=cycle_1_payload)
    )
    await run_cycle()

    async with session_factory() as session:
        row = (
            await session.execute(
                select(ThreadDevice).where(ThreadDevice.ha_device_id == "dev-42")
            )
        ).scalar_one()
    assert row.parent_border_router_id == "br-1"
    assert row.last_seen_parent_id == "br-1"

    monkeypatch.setattr(
        ha_client, "thread_status", AsyncMock(return_value=cycle_2_payload)
    )
    await run_cycle()

    async with session_factory() as session:
        row = (
            await session.execute(
                select(ThreadDevice).where(ThreadDevice.ha_device_id == "dev-42")
            )
        ).scalar_one()

    # Current parent is null (orphaned) but the last-known parent was preserved.
    assert row.parent_border_router_id is None
    assert row.last_seen_parent_id == "br-1"
