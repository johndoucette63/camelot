"""Tests for /settings/thresholds endpoints (User Story 2)."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.alert_threshold import AlertThreshold
from app.routers import settings as settings_router

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Canonical threshold seed — mirrors the production Alembic migration.
THRESHOLD_SEED = [
    {
        "key": "cpu_percent",
        "value": Decimal("80"),
        "unit": "%",
        "default_value": Decimal("80"),
        "min_value": Decimal("10"),
        "max_value": Decimal("100"),
    },
    {
        "key": "disk_percent",
        "value": Decimal("85"),
        "unit": "%",
        "default_value": Decimal("85"),
        "min_value": Decimal("10"),
        "max_value": Decimal("100"),
    },
    {
        "key": "service_down_minutes",
        "value": Decimal("5"),
        "unit": "minutes",
        "default_value": Decimal("5"),
        "min_value": Decimal("1"),
        "max_value": Decimal("1440"),
    },
    {
        "key": "device_offline_minutes",
        "value": Decimal("10"),
        "unit": "minutes",
        "default_value": Decimal("10"),
        "min_value": Decimal("1"),
        "max_value": Decimal("1440"),
    },
]


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

    # The settings router uses `async_session` directly (module-level).
    original = settings_router.async_session
    settings_router.async_session = session_factory

    # Seed the four canonical threshold rows.
    async with session_factory() as session:
        now = _now()
        for row in THRESHOLD_SEED:
            session.add(AlertThreshold(updated_at=now, **row))
        await session.commit()

    async with session_factory() as session:
        yield session

    settings_router.async_session = original
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── (a) GET returns all seeded rows ────────────────────────────────────


@pytest.mark.asyncio
async def test_list_thresholds_returns_all_seeded(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/settings/thresholds")

    assert resp.status_code == 200
    body = resp.json()
    assert "thresholds" in body

    rows = body["thresholds"]
    assert len(rows) == 4

    by_key = {r["key"]: r for r in rows}
    assert set(by_key.keys()) == {
        "cpu_percent",
        "disk_percent",
        "service_down_minutes",
        "device_offline_minutes",
    }

    assert by_key["cpu_percent"]["value"] == 80
    assert by_key["cpu_percent"]["unit"] == "%"
    assert by_key["cpu_percent"]["min_value"] == 10
    assert by_key["cpu_percent"]["max_value"] == 100

    assert by_key["disk_percent"]["value"] == 85
    assert by_key["disk_percent"]["min_value"] == 10
    assert by_key["disk_percent"]["max_value"] == 100

    assert by_key["service_down_minutes"]["value"] == 5
    assert by_key["service_down_minutes"]["unit"] == "minutes"
    assert by_key["service_down_minutes"]["min_value"] == 1
    assert by_key["service_down_minutes"]["max_value"] == 1440

    assert by_key["device_offline_minutes"]["value"] == 10
    assert by_key["device_offline_minutes"]["min_value"] == 1
    assert by_key["device_offline_minutes"]["max_value"] == 1440


# ── (b) PUT updates and GET reflects new value ─────────────────────────


@pytest.mark.asyncio
async def test_put_threshold_updates_value(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/settings/thresholds/cpu_percent", json={"value": 92}
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["key"] == "cpu_percent"
        assert updated["value"] == 92

        # Next GET reflects the new value.
        resp2 = await client.get("/settings/thresholds")
        rows = {r["key"]: r for r in resp2.json()["thresholds"]}
        assert rows["cpu_percent"]["value"] == 92
        # Other rows untouched.
        assert rows["disk_percent"]["value"] == 85


# ── (c) Out-of-range value returns 400 with helpful detail ─────────────


@pytest.mark.asyncio
async def test_put_threshold_out_of_range_returns_400(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # cpu_percent valid range is 10..100
        resp = await client.put(
            "/settings/thresholds/cpu_percent", json={"value": 150}
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "10" in detail
    assert "100" in detail
    assert "between" in detail.lower()


@pytest.mark.asyncio
async def test_put_threshold_below_minimum_returns_400(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/settings/thresholds/disk_percent", json={"value": 5}
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "10" in detail and "100" in detail


# ── (d) Unknown key returns 404 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_threshold_unknown_key_returns_404(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/settings/thresholds/nonexistent_key", json={"value": 42}
        )

    assert resp.status_code == 404
    assert "nonexistent_key" in resp.json()["detail"]
