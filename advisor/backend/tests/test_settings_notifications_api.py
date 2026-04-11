"""Tests for /settings/notifications endpoints (User Story 5)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.notification_sink import NotificationSink
from app.routers import settings as settings_router
from app.routers.settings import mask_endpoint
from app.services import notification_sender

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

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    original = settings_router.async_session
    settings_router.async_session = session_factory

    async with session_factory() as session:
        yield session_factory, session

    settings_router.async_session = original
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── (a) POST creates a sink; GET returns it masked ─────────────────────


@pytest.mark.asyncio
async def test_post_creates_sink_and_get_masks_endpoint(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "HA",
                "enabled": True,
                "endpoint": "http://homeassistant.holygrail/api/webhook/SECRET-TOKEN-123",
                "min_severity": "warning",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "SECRET-TOKEN-123" not in str(body)
        assert "***" in body["endpoint_masked"]
        assert "endpoint" not in body  # raw URL never leaves the server

        resp2 = await client.get("/settings/notifications")
        assert resp2.status_code == 200
        listed = resp2.json()["sinks"]
        assert len(listed) == 1
        assert "SECRET-TOKEN-123" not in str(listed[0])
        assert "***" in listed[0]["endpoint_masked"]


# ── (b) mask_endpoint round-trip ────────────────────────────────────────


def test_mask_endpoint_redacts_webhook_token():
    url = "http://homeassistant.holygrail/api/webhook/SECRET-TOKEN-123"
    masked = mask_endpoint(url)
    assert "SECRET-TOKEN-123" not in masked
    assert "***" in masked
    assert "homeassistant.holygrail" in masked


def test_mask_endpoint_redacts_query_string():
    url = "http://ha/api/webhook/tkn?api_key=shhh"
    masked = mask_endpoint(url)
    assert "shhh" not in masked
    assert "tkn" not in masked
    assert "***" in masked


# ── (c) PUT preserves stored endpoint when omitted ─────────────────────


@pytest.mark.asyncio
async def test_put_without_endpoint_preserves_stored_value(db_and_override):
    session_factory, _ = db_and_override
    stored_url = "http://ha.holygrail/api/webhook/DO-NOT-TOUCH"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "HA",
                "enabled": False,
                "endpoint": stored_url,
                "min_severity": "critical",
            },
        )
        sink_id = resp.json()["id"]

        # Partial PUT toggles enabled without sending endpoint.
        resp2 = await client.put(
            f"/settings/notifications/{sink_id}",
            json={"enabled": True},
        )
        assert resp2.status_code == 200
        assert resp2.json()["enabled"] is True

    # Verify directly via the DB.
    async with session_factory() as session:
        row = await session.get(NotificationSink, sink_id)
        assert row is not None
        assert row.enabled is True
        assert row.endpoint == stored_url


# ── (d) PUT with a new endpoint replaces the stored one ────────────────


@pytest.mark.asyncio
async def test_put_with_new_endpoint_replaces_stored_value(db_and_override):
    session_factory, _ = db_and_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "HA",
                "enabled": False,
                "endpoint": "http://ha/api/webhook/OLD",
                "min_severity": "critical",
            },
        )
        sink_id = resp.json()["id"]

        new_url = "http://ha/api/webhook/NEW-TOKEN"
        resp2 = await client.put(
            f"/settings/notifications/{sink_id}",
            json={"endpoint": new_url},
        )
        assert resp2.status_code == 200

    async with session_factory() as session:
        row = await session.get(NotificationSink, sink_id)
        assert row is not None
        assert row.endpoint == new_url


# ── (e) DELETE returns 204 and the row is gone ─────────────────────────


@pytest.mark.asyncio
async def test_delete_sink_returns_204_and_row_is_gone(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "HA",
                "enabled": True,
                "endpoint": "http://ha/api/webhook/t",
                "min_severity": "critical",
            },
        )
        sink_id = resp.json()["id"]

        resp2 = await client.delete(f"/settings/notifications/{sink_id}")
        assert resp2.status_code == 204

        resp3 = await client.get("/settings/notifications")
        assert resp3.status_code == 200
        assert resp3.json()["sinks"] == []


# ── (f) test endpoint success path ─────────────────────────────────────


@pytest.mark.asyncio
async def test_test_endpoint_success(db_and_override, monkeypatch):
    async def fake_send_test(sink):
        return {"ok": True, "status_code": 200, "latency_ms": 42}

    monkeypatch.setattr(notification_sender, "send_test", fake_send_test)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "HA",
                "enabled": True,
                "endpoint": "http://ha/api/webhook/t",
                "min_severity": "critical",
            },
        )
        sink_id = create.json()["id"]

        resp = await client.post(f"/settings/notifications/{sink_id}/test")
        assert resp.status_code == 200
        assert resp.json() == {
            "ok": True,
            "status_code": 200,
            "latency_ms": 42,
        }


# ── (g) test endpoint failure path ─────────────────────────────────────


@pytest.mark.asyncio
async def test_test_endpoint_failure(db_and_override, monkeypatch):
    async def fake_send_test(sink):
        return {"ok": False, "error": "connection refused"}

    monkeypatch.setattr(notification_sender, "send_test", fake_send_test)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "HA",
                "enabled": True,
                "endpoint": "http://ha/api/webhook/t",
                "min_severity": "critical",
            },
        )
        sink_id = create.json()["id"]

        resp = await client.post(f"/settings/notifications/{sink_id}/test")
        assert resp.status_code == 502
        assert resp.json() == {
            "ok": False,
            "error": "connection refused",
        }
