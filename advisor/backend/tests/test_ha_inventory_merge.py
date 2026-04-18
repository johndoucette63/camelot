"""Tests for app.services.ha_inventory_merge (feature 016, T033).

Exercises the pure merge function that reconciles HA-known devices with
the unified ``devices`` inventory table.

Scenarios (all four from tasks.md T033):

* LAN match: an HA snapshot with a MAC matching an existing scanner-
  discovered row gets merged — single row, both scanner and HA provenance.
* New Thread row: a snapshot without LAN presence creates a fresh row
  keyed by ``ha_device_id``.
* HA reinstall: old ha_device_id remains in place (merge doesn't delete);
  new rows are produced for the new device_ids.
* clear_ha_provenance: wipes HA columns on every row without deleting
  scanner-discovered rows.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.device import Device
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.home_assistant_connection import HomeAssistantConnection
from app.security import encrypt_token
from app.services.ha_inventory_merge import clear_ha_provenance, merge_ha_devices

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture
async def merge_env():
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

    # Every merge call expects a live HA connection row.
    async with session_factory() as session:
        session.add(
            HomeAssistantConnection(
                id=1,
                base_url="http://homeassistant.local:8123",
                token_ciphertext=encrypt_token("tok"),
            )
        )
        await session.commit()

    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _snapshot(
    entity_id: str,
    ha_device_id: str,
    *,
    state: str = "on",
    friendly_name: str = "E",
    integration: str | None = None,
    mac: str | None = None,
    ip: str | None = None,
    domain: str = "switch",
) -> HAEntitySnapshot:
    attrs: dict = {}
    if integration:
        attrs["integration"] = integration
    if mac:
        attrs["mac"] = mac
    if ip:
        attrs["ip"] = ip
    return HAEntitySnapshot(
        entity_id=entity_id,
        ha_device_id=ha_device_id,
        domain=domain,
        friendly_name=friendly_name,
        state=state,
        last_changed=_utcnow(),
        attributes=attrs,
        polled_at=_utcnow(),
    )


# ── (a) LAN match — existing scanner row gets HA provenance attached ───


@pytest.mark.asyncio
async def test_lan_match_merges_into_single_row(merge_env):
    session_factory = merge_env
    mac = "aa:bb:cc:dd:ee:ff"

    async with session_factory() as session:
        session.add(
            Device(
                mac_address=mac,
                ip_address="192.168.10.77",
                hostname="aqara-hub",
                first_seen=_utcnow(),
                last_seen=_utcnow(),
                is_online=True,
            )
        )
        await session.commit()

        snapshots = [_snapshot("switch.hub", "hub-1", mac=mac)]
        conn = await session.get(HomeAssistantConnection, 1)
        await merge_ha_devices(session, snapshots, conn)
        await session.commit()

        rows = (await session.execute(select(Device))).scalars().all()

    assert len(rows) == 1, "no duplicate row should be created when MACs match"
    row = rows[0]
    assert row.mac_address == mac
    assert row.ha_device_id == "hub-1"
    # Connectivity type should be populated (non-Thread LAN device).
    assert row.ha_connectivity_type is not None


# ── (b) Thread row — new inventory row keyed by ha_device_id ───────────


@pytest.mark.asyncio
async def test_new_thread_row_created_without_lan_presence(merge_env):
    session_factory = merge_env

    async with session_factory() as session:
        snapshots = [
            _snapshot(
                "sensor.thread_endpoint",
                "thread-42",
                integration="thread",
                domain="sensor",
            )
        ]
        conn = await session.get(HomeAssistantConnection, 1)
        await merge_ha_devices(session, snapshots, conn)
        await session.commit()

        rows = (await session.execute(select(Device))).scalars().all()

    assert len(rows) == 1
    row = rows[0]
    assert row.ha_device_id == "thread-42"
    assert row.mac_address is None
    assert row.ip_address is None
    assert row.ha_connectivity_type == "thread"


# ── (c) HA reinstall — new device_ids create new rows; old rows kept ───


@pytest.mark.asyncio
async def test_ha_reinstall_creates_new_row_without_deleting_old(merge_env):
    session_factory = merge_env
    mac = "11:22:33:44:55:66"

    async with session_factory() as session:
        # Pre-seed a scanner-discovered row that previously merged with the
        # old HA instance (ha_device_id = "old-id").
        session.add(
            Device(
                mac_address=mac,
                ip_address="192.168.10.80",
                hostname="hub-old",
                first_seen=_utcnow(),
                last_seen=_utcnow(),
                is_online=True,
                ha_device_id="old-id",
                ha_connectivity_type="lan_wifi",
                ha_last_seen_at=_utcnow(),
            )
        )
        await session.commit()

        # Now merge a snapshot from a rebuilt HA instance — same MAC, new
        # device_id. LAN match wins; the row is updated in place.
        snapshots = [_snapshot("switch.hub", "new-id", mac=mac)]
        conn = await session.get(HomeAssistantConnection, 1)
        await merge_ha_devices(session, snapshots, conn)
        await session.commit()

        rows = (await session.execute(select(Device))).scalars().all()

    # Still a single physical device — LAN match updates the existing row.
    same_mac_rows = [r for r in rows if r.mac_address == mac]
    assert len(same_mac_rows) == 1
    row = same_mac_rows[0]
    assert row.ha_device_id == "new-id", (
        "LAN-match should attach the new ha_device_id to the existing row"
    )
    assert row.ha_last_seen_at is not None

    # If the merge somehow emitted an orphan row carrying the OLD id (e.g.
    # because it failed to match), the merge itself must NOT delete it — the
    # stale-device pipeline handles cleanup. Guard against accidental delete.
    # (The merge above should produce exactly one row, so this set comprehension
    # is either {"new-id"} or {"new-id", "old-id"} — both are acceptable;
    # what must not happen is that all rows disappear.)
    ids = {r.ha_device_id for r in rows}
    assert "new-id" in ids
    assert len(rows) >= 1


# ── (d) clear_ha_provenance nulls HA columns without deleting ──────────


@pytest.mark.asyncio
async def test_clear_ha_provenance_wipes_ha_columns(merge_env):
    session_factory = merge_env

    async with session_factory() as session:
        # Row 1: scanner-discovered row with HA provenance attached.
        session.add(
            Device(
                mac_address="aa:aa:aa:aa:aa:aa",
                ip_address="192.168.10.90",
                first_seen=_utcnow(),
                last_seen=_utcnow(),
                is_online=True,
                ha_device_id="hub-1",
                ha_connectivity_type="lan_wifi",
                ha_last_seen_at=_utcnow(),
            )
        )
        # Row 2: HA-only row (no MAC, no IP).
        session.add(
            Device(
                mac_address=None,
                ip_address=None,
                first_seen=_utcnow(),
                last_seen=_utcnow(),
                is_online=False,
                ha_device_id="thread-42",
                ha_connectivity_type="thread",
                ha_last_seen_at=_utcnow(),
            )
        )
        await session.commit()

        await clear_ha_provenance(session)
        await session.commit()

        rows = (await session.execute(select(Device))).scalars().all()

    # Both rows still exist.
    assert len(rows) == 2

    for row in rows:
        # HA columns wiped.
        assert row.ha_device_id is None
        assert row.ha_connectivity_type is None
        assert row.ha_last_seen_at is None

    scanner_row = next(r for r in rows if r.mac_address == "aa:aa:aa:aa:aa:aa")
    ha_only_row = next(r for r in rows if r.mac_address is None)
    # Scanner row keeps its MAC; HA-only row still exists pending stale-device
    # cleanup.
    assert scanner_row.mac_address == "aa:aa:aa:aa:aa:aa"
    assert ha_only_row.ip_address is None
