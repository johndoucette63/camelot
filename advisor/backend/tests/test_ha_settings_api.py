"""Tests for /settings/home-assistant endpoints (feature 016, T034).

Exercises the four endpoints in contracts/home-assistant-api.md §1:

* ``GET /settings/home-assistant`` — redacted read-back
* ``PUT /settings/home-assistant`` — validate-then-save
* ``POST /settings/home-assistant/test-connection`` — no persist
* ``DELETE /settings/home-assistant`` — clears connection + HA provenance

Verifies:

1. PUT with a token that HA rejects returns 400 with ``status=auth_failure``
   and does NOT persist (base_url stays NULL).
2. PUT with a good token returns 200 with ``HAConnectionRead`` shape, the
   masked token ends in the last 4 chars of the plaintext, and the row is
   populated (token ciphertext non-null).
3. GET never serialises the plaintext token in the response body.
4. DELETE clears the singleton's columns AND invokes ``clear_ha_provenance``
   (verified by seeding a device with HA columns and asserting they are
   nulled).
5. POST /test-connection does not persist even on success.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.device import Device
from app.models.home_assistant_connection import HomeAssistantConnection
from app.routers import settings as settings_router
from app.services import ha_client
from app.services.ha_client import HAAuthError

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

GOOD_TOKEN = "llat_plaintext123456"


def _utcnow():
    from datetime import datetime, timezone

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

    # Seed the singleton row — every deployment has id=1 from migration.
    async with session_factory() as session:
        session.add(HomeAssistantConnection(id=1))
        await session.commit()

    # Most routers read the module-level ``async_session`` directly.
    original = settings_router.async_session
    settings_router.async_session = session_factory

    yield session_factory

    settings_router.async_session = original
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── (a) PUT with bad token → 400 + auth_failure, nothing persisted ─────


@pytest.mark.asyncio
async def test_put_bad_token_returns_400_auth_failure(db_and_override, monkeypatch):
    session_factory = db_and_override

    monkeypatch.setattr(
        ha_client,
        "ping",
        AsyncMock(side_effect=HAAuthError("Home Assistant rejected the token (HTTP 401).")),
    )

    async with await _client() as client:
        resp = await client.put(
            "/settings/home-assistant",
            json={
                "base_url": "http://homeassistant.local:8123",
                "access_token": "llat_bogus",
            },
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body.get("status") == "auth_failure"

    async with session_factory() as session:
        row = await session.get(HomeAssistantConnection, 1)
    assert row.base_url is None
    assert row.token_ciphertext is None


# ── (b) PUT with good token → 200 + persisted, masked token returned ───


@pytest.mark.asyncio
async def test_put_good_token_persists_and_returns_masked(db_and_override, monkeypatch):
    session_factory = db_and_override

    monkeypatch.setattr(
        ha_client, "ping", AsyncMock(return_value={"message": "API running."})
    )

    async with await _client() as client:
        resp = await client.put(
            "/settings/home-assistant",
            json={
                "base_url": "http://homeassistant.local:8123",
                "access_token": GOOD_TOKEN,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["configured"] is True
    assert body["base_url"] == "http://homeassistant.local:8123"

    # token_masked ends with the last 4 chars of the plaintext.
    assert body["token_masked"]
    assert body["token_masked"].endswith(GOOD_TOKEN[-4:])
    # And the plaintext never appears in the response body.
    assert GOOD_TOKEN not in str(body)

    async with session_factory() as session:
        row = await session.get(HomeAssistantConnection, 1)
    assert row.base_url == "http://homeassistant.local:8123"
    assert row.token_ciphertext is not None
    assert isinstance(row.token_ciphertext, (bytes, bytearray))


# ── (c) GET never returns plaintext ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_never_returns_plaintext_token(db_and_override, monkeypatch):
    monkeypatch.setattr(
        ha_client, "ping", AsyncMock(return_value={"message": "API running."})
    )

    async with await _client() as client:
        put_resp = await client.put(
            "/settings/home-assistant",
            json={
                "base_url": "http://homeassistant.local:8123",
                "access_token": GOOD_TOKEN,
            },
        )
        assert put_resp.status_code == 200

        get_resp = await client.get("/settings/home-assistant")

    assert get_resp.status_code == 200
    body_text = get_resp.text
    assert GOOD_TOKEN not in body_text
    body = get_resp.json()
    # Masked read-back is present.
    assert body.get("token_masked")
    assert body["token_masked"].endswith(GOOD_TOKEN[-4:])


# ── (d) DELETE clears connection + HA provenance ───────────────────────


@pytest.mark.asyncio
async def test_delete_clears_connection_and_provenance(db_and_override, monkeypatch):
    session_factory = db_and_override

    monkeypatch.setattr(
        ha_client, "ping", AsyncMock(return_value={"message": "API running."})
    )

    # Seed a device with HA provenance so we can observe clear_ha_provenance.
    async with session_factory() as session:
        session.add(
            Device(
                mac_address="aa:bb:cc:dd:ee:ff",
                ip_address="192.168.10.77",
                first_seen=_utcnow(),
                last_seen=_utcnow(),
                is_online=True,
                ha_device_id="hub-1",
                ha_connectivity_type="lan_wifi",
                ha_last_seen_at=_utcnow(),
            )
        )
        await session.commit()

    async with await _client() as client:
        await client.put(
            "/settings/home-assistant",
            json={
                "base_url": "http://homeassistant.local:8123",
                "access_token": GOOD_TOKEN,
            },
        )

        del_resp = await client.delete("/settings/home-assistant")
        assert del_resp.status_code in (200, 204)

        # GET after DELETE shows unconfigured.
        get_resp = await client.get("/settings/home-assistant")

    body = get_resp.json()
    assert body.get("configured") is False

    # Device row still exists but HA columns are nulled.
    async with session_factory() as session:
        rows = (await session.execute(select(Device))).scalars().all()
    assert len(rows) == 1
    assert rows[0].ha_device_id is None
    assert rows[0].ha_connectivity_type is None
    assert rows[0].ha_last_seen_at is None


# ── (e) POST /test-connection does not persist ─────────────────────────


@pytest.mark.asyncio
async def test_post_test_connection_does_not_persist(db_and_override, monkeypatch):
    session_factory = db_and_override

    monkeypatch.setattr(
        ha_client, "ping", AsyncMock(return_value={"message": "API running."})
    )

    async with await _client() as client:
        resp = await client.post(
            "/settings/home-assistant/test-connection",
            json={
                "base_url": "http://homeassistant.local:8123",
                "access_token": GOOD_TOKEN,
            },
        )

    assert resp.status_code == 200

    async with session_factory() as session:
        row = await session.get(HomeAssistantConnection, 1)
    # Row remains unconfigured — the test endpoint must never persist.
    assert row.base_url is None
    assert row.token_ciphertext is None


# ── Sink variant tests (feature 016, US-3 / T060) ──────────────────────
#
# Verify the new HA-native notify-sink shape on the existing
# /settings/notifications endpoint and the new
# /settings/notifications/available-ha-services endpoint.


async def _configure_ha(client, monkeypatch) -> None:
    """Helper: PUT a valid HA connection via the mocked ping."""
    monkeypatch.setattr(
        ha_client, "ping", AsyncMock(return_value={"message": "API running."})
    )
    resp = await client.put(
        "/settings/home-assistant",
        json={
            "base_url": "http://homeassistant.local:8123",
            "access_token": GOOD_TOKEN,
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_post_sink_ha_native_persists_with_fk(db_and_override, monkeypatch):
    """POST with a bare service suffix links home_assistant_id=1."""
    from app.models.notification_sink import NotificationSink

    session_factory = db_and_override

    async with await _client() as client:
        await _configure_ha(client, monkeypatch)

        resp = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "Phone (HA push)",
                "enabled": True,
                "endpoint": "mobile_app_pixel9",
                "min_severity": "critical",
            },
        )

    assert resp.status_code == 201, resp.text

    async with session_factory() as session:
        from sqlalchemy import select

        sinks = (await session.execute(select(NotificationSink))).scalars().all()
    assert len(sinks) == 1
    assert sinks[0].home_assistant_id == 1
    assert sinks[0].endpoint == "mobile_app_pixel9"
    assert sinks[0].type == "home_assistant"


@pytest.mark.asyncio
async def test_post_sink_ha_native_strips_notify_prefix(
    db_and_override, monkeypatch
):
    """Canonical naming — ``notify.mobile_app_pixel9`` is stored bare."""
    from app.models.notification_sink import NotificationSink

    session_factory = db_and_override

    async with await _client() as client:
        await _configure_ha(client, monkeypatch)

        resp = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "Phone (HA push)",
                "enabled": True,
                "endpoint": "notify.mobile_app_pixel9",
                "min_severity": "critical",
            },
        )

    assert resp.status_code == 201, resp.text

    async with session_factory() as session:
        from sqlalchemy import select

        row = (
            await session.execute(select(NotificationSink))
        ).scalar_one()
    assert row.endpoint == "mobile_app_pixel9"


@pytest.mark.asyncio
async def test_post_sink_ha_native_400_when_no_ha_connection(db_and_override):
    """POST HA-native sink without a configured HA connection → 400."""
    async with await _client() as client:
        resp = await client.post(
            "/settings/notifications",
            json={
                "type": "home_assistant",
                "name": "Phone (HA push)",
                "enabled": True,
                "endpoint": "mobile_app_pixel9",
                "min_severity": "critical",
            },
        )

    assert resp.status_code == 400
    body = resp.json()
    assert "home assistant" in body.get("detail", "").lower()


@pytest.mark.asyncio
async def test_available_ha_services_ok_returns_list(db_and_override, monkeypatch):
    """GET available-ha-services returns the bare service-name list."""
    async with await _client() as client:
        await _configure_ha(client, monkeypatch)

        monkeypatch.setattr(
            ha_client,
            "list_notify_services",
            AsyncMock(
                return_value=[
                    "mobile_app_pixel9",
                    "mobile_app_ipad",
                    "persistent_notification",
                ]
            ),
        )

        resp = await client.get("/settings/notifications/available-ha-services")

    assert resp.status_code == 200
    body = resp.json()
    assert body["services"] == [
        "mobile_app_pixel9",
        "mobile_app_ipad",
        "persistent_notification",
    ]


@pytest.mark.asyncio
async def test_available_ha_services_409_when_unreachable(
    db_and_override, monkeypatch
):
    """GET available-ha-services returns 409 when HA is unreachable."""
    from app.services.ha_client import HAUnreachableError

    async with await _client() as client:
        await _configure_ha(client, monkeypatch)

        monkeypatch.setattr(
            ha_client,
            "list_notify_services",
            AsyncMock(side_effect=HAUnreachableError("HA down")),
        )

        resp = await client.get("/settings/notifications/available-ha-services")

    assert resp.status_code == 409
    assert "home assistant" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_available_ha_services_409_when_not_configured(db_and_override):
    """GET available-ha-services returns 409 when no HA connection exists."""
    async with await _client() as client:
        resp = await client.get("/settings/notifications/available-ha-services")

    assert resp.status_code == 409
