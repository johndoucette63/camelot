"""Tests for GET /dashboard/summary endpoint."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.health_check_result import HealthCheckResult
from app.models.service_definition import ServiceDefinition
from app.routers.dashboard import get_db

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
    app.state.hosts_unreachable = set()

    async with session_factory() as session:
        yield session

    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _seed(db: AsyncSession, name: str, host_label: str, status: str | None = None):
    svc = ServiceDefinition(
        name=name, host_label=host_label, host="192.168.10.1", port=8000,
        check_type="http", check_url="/health", degraded_threshold_ms=2000,
        enabled=True,
    )
    db.add(svc)
    await db.flush()
    if status:
        db.add(HealthCheckResult(service_id=svc.id, checked_at=_now(), status=status, response_time_ms=50))
    await db.commit()
    return svc


@pytest.mark.asyncio
async def test_all_healthy(db_and_override):
    db = db_and_override
    await _seed(db, "Plex", "HOLYGRAIL", "green")
    await _seed(db, "Grafana", "HOLYGRAIL", "green")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/summary")

    data = resp.json()
    assert data["total"] == 2
    assert data["healthy"] == 2
    assert data["degraded"] == 0
    assert data["down"] == 0
    assert data["unchecked"] == 0


@pytest.mark.asyncio
async def test_mixed_statuses(db_and_override):
    db = db_and_override
    await _seed(db, "Plex", "HOLYGRAIL", "green")
    await _seed(db, "Deluge", "Torrentbox", "red")
    await _seed(db, "Sonarr", "Torrentbox", "yellow")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/summary")

    data = resp.json()
    assert data["total"] == 3
    assert data["healthy"] == 1
    assert data["degraded"] == 1
    assert data["down"] == 1


@pytest.mark.asyncio
async def test_unchecked_services_counted(db_and_override):
    db = db_and_override
    await _seed(db, "Plex", "HOLYGRAIL", "green")
    await _seed(db, "NewService", "HOLYGRAIL")  # no check result

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/summary")

    data = resp.json()
    assert data["unchecked"] == 1
    assert data["healthy"] == 1


@pytest.mark.asyncio
async def test_per_host_breakdown_correct(db_and_override):
    db = db_and_override
    await _seed(db, "Plex", "HOLYGRAIL", "green")
    await _seed(db, "Grafana", "HOLYGRAIL", "green")
    await _seed(db, "Deluge", "Torrentbox", "red")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/summary")

    data = resp.json()
    hosts = {h["label"]: h for h in data["hosts"]}
    assert hosts["HOLYGRAIL"]["total"] == 2
    assert hosts["HOLYGRAIL"]["healthy"] == 2
    assert hosts["Torrentbox"]["total"] == 1
    assert hosts["Torrentbox"]["down"] == 1


@pytest.mark.asyncio
async def test_host_level_unreachable(db_and_override):
    db = db_and_override
    await _seed(db, "Deluge", "Torrentbox", "red")
    app.state.hosts_unreachable = {"Torrentbox"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/summary")

    data = resp.json()
    assert "Torrentbox" in data["hosts_unreachable"]

    # Cleanup
    app.state.hosts_unreachable = set()


@pytest.mark.asyncio
async def test_host_not_unreachable_when_some_respond(db_and_override):
    db = db_and_override
    await _seed(db, "Deluge", "Torrentbox", "red")
    await _seed(db, "Sonarr", "Torrentbox", "green")
    app.state.hosts_unreachable = set()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/summary")

    data = resp.json()
    assert data["hosts_unreachable"] == []
