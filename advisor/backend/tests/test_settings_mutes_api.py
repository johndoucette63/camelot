"""Tests for /settings/mutes endpoints (User Story 2)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.device import Device
from app.models.rule_mute import RuleMute
from app.routers import settings as settings_router

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
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

    original = settings_router.async_session
    settings_router.async_session = session_factory

    # Seed one device so target_id lookups can resolve a label.
    async with session_factory() as session:
        now = _now()
        device = Device(
            mac_address="AA:BB:CC:11:22:33",
            ip_address="192.168.10.200",
            hostname="testhost",
            first_seen=now,
            last_seen=now,
            is_online=True,
            consecutive_missed_scans=0,
            is_known_device=True,
        )
        session.add(device)
        await session.commit()
        await session.refresh(device)
        device_id = device.id

    async with session_factory() as session:
        yield session, device_id, session_factory

    settings_router.async_session = original
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── (a) Create/list/delete round-trip ──────────────────────────────────


@pytest.mark.asyncio
async def test_create_list_delete_mute_roundtrip(db_and_override):
    _session, device_id, session_factory = db_and_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create
        create_resp = await client.post(
            "/settings/mutes",
            json={
                "rule_id": "disk_high",
                "target_type": "device",
                "target_id": device_id,
                "duration_seconds": 3600,
                "note": "rebooting nas for upgrade",
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        mute_id = created["id"]
        assert created["rule_id"] == "disk_high"
        assert created["target_type"] == "device"
        assert created["target_id"] == device_id
        assert created["note"] == "rebooting nas for upgrade"
        assert created["remaining_seconds"] > 0
        assert created["remaining_seconds"] <= 3600
        # target_label resolved from seeded device hostname.
        assert created["target_label"] == "testhost"

        # List (default — hides expired/cancelled)
        list_resp = await client.get("/settings/mutes")
        assert list_resp.status_code == 200
        listing = list_resp.json()["mutes"]
        assert len(listing) == 1
        assert listing[0]["id"] == mute_id

        # Delete
        del_resp = await client.delete(f"/settings/mutes/{mute_id}")
        assert del_resp.status_code == 204

        # After delete, default list should be empty.
        list_resp2 = await client.get("/settings/mutes")
        assert list_resp2.json()["mutes"] == []

    # And the row should have cancelled_at set in the DB.
    async with session_factory() as session:
        row = await session.get(RuleMute, mute_id)
        assert row is not None
        assert row.cancelled_at is not None


# ── (b) duration_seconds > 7 days rejected ─────────────────────────────


@pytest.mark.asyncio
async def test_create_mute_duration_too_long_rejected(db_and_override):
    _session, device_id, _factory = db_and_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/mutes",
            json={
                "rule_id": "disk_high",
                "target_type": "device",
                "target_id": device_id,
                "duration_seconds": 604801,  # one second over 7 days
            },
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "7" in detail or "604800" in detail


# ── (c) target_type='system' with target_id set → 400 ──────────────────


@pytest.mark.asyncio
async def test_create_mute_system_with_target_id_rejected(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/mutes",
            json={
                "rule_id": "ollama_unavailable",
                "target_type": "system",
                "target_id": 5,
                "duration_seconds": 600,
            },
        )

    assert resp.status_code == 400
    assert "target_id" in resp.json()["detail"]


# ── (d) target_type='device' without target_id → 400 ───────────────────


@pytest.mark.asyncio
async def test_create_mute_device_without_target_id_rejected(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/mutes",
            json={
                "rule_id": "disk_high",
                "target_type": "device",
                "target_id": None,
                "duration_seconds": 600,
            },
        )

    assert resp.status_code == 400
    assert "target_id" in resp.json()["detail"]


# ── (e) Double-delete is idempotent ────────────────────────────────────


@pytest.mark.asyncio
async def test_double_delete_mute_is_idempotent(db_and_override):
    _session, device_id, session_factory = db_and_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create = await client.post(
            "/settings/mutes",
            json={
                "rule_id": "disk_high",
                "target_type": "device",
                "target_id": device_id,
                "duration_seconds": 600,
            },
        )
        mute_id = create.json()["id"]

        first = await client.delete(f"/settings/mutes/{mute_id}")
        assert first.status_code == 204

        # Fetch cancelled_at after the first delete.
        async with session_factory() as session:
            row_after_first = await session.get(RuleMute, mute_id)
            assert row_after_first is not None
            first_cancelled_at = row_after_first.cancelled_at
            assert first_cancelled_at is not None

        second = await client.delete(f"/settings/mutes/{mute_id}")
        assert second.status_code == 204

        # The row should still exist with the same cancelled_at (not re-stamped).
        async with session_factory() as session:
            row_after_second = await session.get(RuleMute, mute_id)
            assert row_after_second is not None
            assert row_after_second.cancelled_at == first_cancelled_at


# ── (f) include_expired filter ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_mutes_include_expired_filter(db_and_override):
    session, device_id, session_factory = db_and_override
    now = _now()

    # Active mute — visible in default list.
    active = RuleMute(
        rule_id="disk_high",
        target_type="device",
        target_id=device_id,
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    # Cancelled mute — hidden by default.
    cancelled = RuleMute(
        rule_id="service_down",
        target_type="device",
        target_id=device_id,
        created_at=now - timedelta(minutes=30),
        expires_at=now + timedelta(hours=1),
        cancelled_at=now - timedelta(minutes=5),
    )
    # Expired mute — hidden by default.
    expired = RuleMute(
        rule_id="pi_cpu_high",
        target_type="device",
        target_id=device_id,
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=1),
    )
    session.add_all([active, cancelled, expired])
    await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        default_resp = await client.get("/settings/mutes")
        assert default_resp.status_code == 200
        default_ids = {m["rule_id"] for m in default_resp.json()["mutes"]}
        assert default_ids == {"disk_high"}

        expired_resp = await client.get("/settings/mutes?include_expired=true")
        assert expired_resp.status_code == 200
        all_ids = {m["rule_id"] for m in expired_resp.json()["mutes"]}
        assert all_ids == {"disk_high", "service_down", "pi_cpu_high"}


# ── (g) Unknown rule_id rejected ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_mute_unknown_rule_id_rejected(db_and_override):
    _session, device_id, _factory = db_and_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/mutes",
            json={
                "rule_id": "nonexistent_rule",
                "target_type": "device",
                "target_id": device_id,
                "duration_seconds": 600,
            },
        )

    assert resp.status_code == 400
    assert "nonexistent_rule" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_mute_accepts_all_known_rule_ids(db_and_override):
    _session, device_id, _factory = db_and_override

    known_ids = [
        "pi_cpu_high",
        "disk_high",
        "service_down",
        "device_offline",
        "ollama_unavailable",
        "unknown_device",
    ]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for rid in known_ids:
            # 'ollama_unavailable' targets system; others targets device for this test.
            if rid == "ollama_unavailable":
                payload = {
                    "rule_id": rid,
                    "target_type": "system",
                    "target_id": None,
                    "duration_seconds": 600,
                }
            else:
                payload = {
                    "rule_id": rid,
                    "target_type": "device",
                    "target_id": device_id,
                    "duration_seconds": 600,
                }
            resp = await client.post("/settings/mutes", json=payload)
            assert resp.status_code == 201, f"{rid} should be accepted: {resp.text}"
