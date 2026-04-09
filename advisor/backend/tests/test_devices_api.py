"""Tests for GET /devices and PATCH /devices/{mac}/annotation endpoints."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.annotation import Annotation
from app.models.device import Device
from app.routers.devices import get_db

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


async def _seed_device(
    db: AsyncSession,
    mac: str,
    ip: str,
    hostname: str = "test",
    is_online: bool = True,
    is_known: bool = False,
    role: str | None = None,
) -> Device:
    device = Device(
        mac_address=mac,
        ip_address=ip,
        hostname=hostname,
        first_seen=_now(),
        last_seen=_now(),
        is_online=is_online,
        consecutive_missed_scans=0,
        is_known_device=is_known,
    )
    db.add(device)
    await db.flush()
    if role:
        ann = Annotation(device_id=device.id, role=role, description=None, tags=[])
        db.add(ann)
    await db.commit()
    return device


@pytest.mark.asyncio
async def test_list_devices_returns_all(db_and_override):
    db = db_and_override
    await _seed_device(db, "AA:BB:CC:00:00:01", "192.168.10.1", role="server")
    await _seed_device(db, "AA:BB:CC:00:00:02", "192.168.10.2", role="workstation")
    await _seed_device(db, "AA:BB:CC:00:00:03", "192.168.10.3")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/devices")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    macs = {d["mac_address"] for d in data}
    assert "AA:BB:CC:00:00:01" in macs
    assert "AA:BB:CC:00:00:02" in macs
    assert "AA:BB:CC:00:00:03" in macs

    # First device has annotation nested
    annotated = next(d for d in data if d["mac_address"] == "AA:BB:CC:00:00:01")
    assert annotated["annotation"]["role"] == "server"


@pytest.mark.asyncio
async def test_filter_by_hostname(db_and_override):
    db = db_and_override
    await _seed_device(db, "BB:CC:DD:00:00:01", "192.168.10.10", hostname="HOLYGRAIL")
    await _seed_device(db, "BB:CC:DD:00:00:02", "192.168.10.11", hostname="Torrentbox")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/devices?q=HOLY")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["hostname"] == "HOLYGRAIL"


@pytest.mark.asyncio
async def test_get_device_by_mac(db_and_override):
    db = db_and_override
    await _seed_device(db, "CC:DD:EE:00:00:01", "192.168.10.20", hostname="myhost", role="dns")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/devices/CC:DD:EE:00:00:01")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mac_address"] == "CC:DD:EE:00:00:01"
    assert data["hostname"] == "myhost"
    assert data["annotation"]["role"] == "dns"


@pytest.mark.asyncio
async def test_get_device_not_found(db_and_override):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/devices/00:00:00:00:00:00")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_annotation_creates_new(db_and_override):
    db = db_and_override
    await _seed_device(db, "DD:EE:FF:00:00:01", "192.168.10.30")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/devices/DD:EE:FF:00:00:01/annotation",
            json={"role": "server", "description": "My server", "tags": ["plex"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["annotation"]["role"] == "server"
    assert data["annotation"]["description"] == "My server"
    assert "plex" in data["annotation"]["tags"]


@pytest.mark.asyncio
async def test_patch_annotation_invalid_role(db_and_override):
    db = db_and_override
    await _seed_device(db, "EE:FF:00:00:00:01", "192.168.10.40")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/devices/EE:FF:00:00:00:01/annotation",
            json={"role": "spaceship"},
        )

    assert resp.status_code == 422
