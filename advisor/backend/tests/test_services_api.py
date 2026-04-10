"""Tests for GET /services and GET /services/{id}/history endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.health_check_result import HealthCheckResult
from app.models.service_definition import ServiceDefinition
from app.routers.services import get_db

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


async def _seed_service(db: AsyncSession, name="Plex", host_label="HOLYGRAIL", host="192.168.10.129", port=32400):
    svc = ServiceDefinition(
        name=name, host_label=host_label, host=host, port=port,
        check_type="http", check_url="/health", degraded_threshold_ms=2000,
        enabled=True,
    )
    db.add(svc)
    await db.flush()
    return svc


@pytest.mark.asyncio
async def test_list_services_returns_latest_status(db_and_override):
    db = db_and_override
    svc = await _seed_service(db)
    # Add two check results — latest should be returned
    db.add(HealthCheckResult(service_id=svc.id, checked_at=_now() - timedelta(minutes=5), status="red", error="down"))
    db.add(HealthCheckResult(service_id=svc.id, checked_at=_now(), status="green", response_time_ms=50))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/services")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Plex"
    assert data[0]["latest"]["status"] == "green"
    assert data[0]["latest"]["response_time_ms"] == 50


@pytest.mark.asyncio
async def test_list_services_pending_when_no_results(db_and_override):
    db = db_and_override
    await _seed_service(db)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/services")

    data = resp.json()
    assert data[0]["latest"] is None


@pytest.mark.asyncio
async def test_history_default_24h(db_and_override):
    db = db_and_override
    svc = await _seed_service(db)
    db.add(HealthCheckResult(service_id=svc.id, checked_at=_now(), status="green", response_time_ms=10))
    db.add(HealthCheckResult(service_id=svc.id, checked_at=_now() - timedelta(hours=25), status="red", error="old"))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/services/{svc.id}/history")

    data = resp.json()
    # Only the recent result (within 24h) should appear
    assert len(data["history"]) == 1
    assert data["history"][0]["status"] == "green"


@pytest.mark.asyncio
async def test_history_custom_hours(db_and_override):
    db = db_and_override
    svc = await _seed_service(db)
    db.add(HealthCheckResult(service_id=svc.id, checked_at=_now(), status="green", response_time_ms=10))
    db.add(HealthCheckResult(service_id=svc.id, checked_at=_now() - timedelta(hours=25), status="red", error="old"))
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/services/{svc.id}/history?hours=48")

    data = resp.json()
    assert len(data["history"]) == 2


@pytest.mark.asyncio
async def test_history_clamps_at_168h(db_and_override):
    db = db_and_override
    svc = await _seed_service(db)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/services/{svc.id}/history?hours=999")

    assert resp.status_code == 422  # validation error: le=168


@pytest.mark.asyncio
async def test_history_404_unknown_service(db_and_override):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/services/99999/history")

    assert resp.status_code == 404
