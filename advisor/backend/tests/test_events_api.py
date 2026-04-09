"""Tests for GET /events endpoint."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.device import Device
from app.models.event import Event
from app.routers.events import get_db

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

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with session_factory() as session:
        yield session

    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _seed_device(db: AsyncSession, mac: str, ip: str) -> Device:
    device = Device(
        mac_address=mac,
        ip_address=ip,
        hostname="testhost",
        first_seen=_now(),
        last_seen=_now(),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=False,
    )
    db.add(device)
    await db.flush()
    return device


@pytest.mark.asyncio
async def test_events_returns_newest_first(db_and_override):
    db = db_and_override
    device = await _seed_device(db, "AA:00:00:00:00:01", "192.168.10.1")

    base = _now()
    for i, etype in enumerate(["new-device", "offline", "back-online"]):
        db.add(Event(
            event_type=etype,
            device_id=device.id,
            timestamp=base + timedelta(minutes=i),
        ))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/events")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    timestamps = [e["timestamp"] for e in data["events"]]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_filter_by_event_type(db_and_override):
    db = db_and_override
    device = await _seed_device(db, "BB:00:00:00:00:01", "192.168.10.2")

    db.add(Event(event_type="offline", device_id=device.id, timestamp=_now()))
    db.add(Event(event_type="new-device", device_id=device.id, timestamp=_now()))
    db.add(Event(event_type="scan-error", timestamp=_now(), details={"error": "timeout"}))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/events?type=offline")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert all(e["event_type"] == "offline" for e in data["events"])


@pytest.mark.asyncio
async def test_events_since_param(db_and_override):
    db = db_and_override
    device = await _seed_device(db, "CC:00:00:00:00:01", "192.168.10.3")

    old_time = _now() - timedelta(hours=48)
    recent_time = _now() - timedelta(hours=1)

    db.add(Event(event_type="offline", device_id=device.id, timestamp=old_time))
    db.add(Event(event_type="back-online", device_id=device.id, timestamp=recent_time))
    await db.commit()

    cutoff = (_now() - timedelta(hours=24)).isoformat()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/events?since={cutoff}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["events"][0]["event_type"] == "back-online"


@pytest.mark.asyncio
async def test_scan_error_event_has_null_device(db_and_override):
    db = db_and_override
    db.add(Event(
        event_type="scan-error",
        device_id=None,
        timestamp=_now(),
        details={"error": "nmap not found"},
    ))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/events?type=scan-error")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["events"][0]["device"] is None
    assert data["events"][0]["details"]["error"] == "nmap not found"
