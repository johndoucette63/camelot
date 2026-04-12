"""Tests for notes CRUD API — T018."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.device import Device
from app.models.note import Note
from app.models.service_definition import ServiceDefinition
from app.routers.notes import get_db

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


async def _seed_device(db: AsyncSession, ip: str = "192.168.10.1") -> Device:
    device = Device(
        mac_address="AA:BB:CC:00:00:01",
        ip_address=ip,
        hostname="testdevice",
        first_seen=_now(),
        last_seen=_now(),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=False,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def _seed_service(db: AsyncSession) -> ServiceDefinition:
    svc = ServiceDefinition(
        name="TestService",
        host_label="testhost",
        host="192.168.10.1",
        port=8080,
        check_type="http",
        enabled=True,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return svc


@pytest.mark.asyncio
async def test_create_device_note(db_and_override):
    db = db_and_override
    device = await _seed_device(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/notes", json={
            "target_type": "device",
            "target_id": device.id,
            "body": "Test note for device",
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["target_type"] == "device"
    assert data["target_id"] == device.id
    assert data["body"] == "Test note for device"
    assert data["pinned"] is False


@pytest.mark.asyncio
async def test_list_notes_by_target(db_and_override):
    db = db_and_override
    device = await _seed_device(db)

    # Add two notes to the device
    for i in range(2):
        db.add(Note(target_type="device", target_id=device.id, body=f"Note {i}"))
    # Add a playbook note (should not appear)
    db.add(Note(target_type="playbook", body="Playbook note"))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/notes?target_type=device&target_id={device.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(n["target_type"] == "device" for n in data["notes"])


@pytest.mark.asyncio
async def test_update_note_body_and_pin(db_and_override):
    db = db_and_override
    note = Note(target_type="playbook", body="Original body")
    db.add(note)
    await db.commit()
    await db.refresh(note)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/notes/{note.id}", json={
            "body": "Updated body",
            "pinned": True,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["body"] == "Updated body"
    assert data["pinned"] is True


@pytest.mark.asyncio
async def test_delete_note(db_and_override):
    db = db_and_override
    note = Note(target_type="playbook", body="To be deleted")
    db.add(note)
    await db.commit()
    await db.refresh(note)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/notes/{note.id}")
    assert resp.status_code == 204

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/notes?target_type=playbook")
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_empty_body_rejected(db_and_override):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/notes", json={
            "target_type": "playbook",
            "body": "",
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_body_exceeds_2kb_rejected(db_and_override):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/notes", json={
            "target_type": "playbook",
            "body": "x" * 2049,
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_pinned_cap_returns_409(db_and_override):
    db = db_and_override
    # Create 20 pinned playbook notes (at the cap)
    for i in range(20):
        db.add(Note(target_type="playbook", body=f"Pinned note {i}", pinned=True))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/notes", json={
            "target_type": "playbook",
            "body": "One more pinned",
            "pinned": True,
        })

    assert resp.status_code == 409
    assert "Maximum" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_device_not_found_returns_404(db_and_override):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/notes", json={
            "target_type": "device",
            "target_id": 9999,
            "body": "Note for missing device",
        })
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skip(reason="jsonb_array_elements_text is PostgreSQL-only; skipped on SQLite")
async def test_tags_autocomplete(db_and_override):
    db = db_and_override
    db.add(Note(target_type="playbook", body="A", tags=["maintenance", "dns"]))
    db.add(Note(target_type="playbook", body="B", tags=["maintenance", "vpn"]))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/notes/tags")

    assert resp.status_code == 200
    tags = resp.json()["tags"]
    assert "maintenance" in tags
    assert "dns" in tags
    assert "vpn" in tags


@pytest.mark.asyncio
async def test_rejected_suggestion_idempotent(db_and_override):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.post("/notes/rejected-suggestions", json={
            "body": "NAS scrub happens Sunday",
        })
        assert resp1.status_code == 200  # 201 first time

        resp2 = await client.post("/notes/rejected-suggestions", json={
            "body": "NAS scrub happens Sunday",
        })
        assert resp2.status_code == 200  # idempotent
        assert resp1.json()["content_hash"] == resp2.json()["content_hash"]
