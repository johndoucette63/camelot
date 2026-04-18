"""Tests for app.services.ha_client (feature 016, T031).

Uses ``httpx.MockTransport`` to simulate Home Assistant REST responses so
the real code paths run end-to-end while the network is stubbed.

Covers:

* Each public method (ping, states, config, services, call_notify) maps a
  200 + valid JSON response to a parsed payload.
* 401 and 403 → HAAuthError.
* 500 / 502 and connection errors / timeouts → HAUnreachableError.
* 200 with non-JSON body → HAUnexpectedPayloadError.
* Every outbound request carries ``Authorization: Bearer <token>``.
* Token plaintext never leaks into any log record (Constitution V).
"""
from __future__ import annotations

import logging

import httpx
import pytest

from app.models.home_assistant_connection import HomeAssistantConnection
from app.security import encrypt_token
from app.services import ha_client
from app.services.ha_client import (
    HAAuthError,
    HAUnexpectedPayloadError,
    HAUnreachableError,
    call_notify,
    config,
    ping,
    services,
    states,
)

TOKEN_PLAINTEXT = "llat_super_secret_value_DEADBEEF"


# ── helpers ────────────────────────────────────────────────────────────


def _make_conn() -> HomeAssistantConnection:
    """Build a detached connection row with an encrypted token.

    The client decrypts via settings.advisor_encryption_key (the conftest
    fixture key), so this round-trips cleanly.
    """
    return HomeAssistantConnection(
        id=1,
        base_url="http://homeassistant.local:8123",
        token_ciphertext=encrypt_token(TOKEN_PLAINTEXT),
    )


def _install_transport(monkeypatch, handler):
    """Swap httpx.AsyncClient for one backed by a MockTransport.

    The real ha_client code constructs ``httpx.AsyncClient(timeout=...)``
    inside ``_request``; patch the class in that module's namespace so the
    mock transport is picked up without changing production code.
    """
    original = ha_client.httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(ha_client.httpx, "AsyncClient", factory)


# ── (a) happy path: each method parses a valid JSON payload ────────────


@pytest.mark.asyncio
async def test_ping_success(monkeypatch):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/"
        assert request.headers["Authorization"] == f"Bearer {TOKEN_PLAINTEXT}"
        return httpx.Response(200, json={"message": "API running."})

    _install_transport(monkeypatch, handler)
    result = await ping(conn)
    assert result == {"message": "API running."}


@pytest.mark.asyncio
async def test_states_success(monkeypatch):
    conn = _make_conn()

    sample = [
        {"entity_id": "binary_sensor.front_door", "state": "off", "attributes": {}},
        {"entity_id": "switch.lamp", "state": "on", "attributes": {}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states"
        return httpx.Response(200, json=sample)

    _install_transport(monkeypatch, handler)
    result = await states(conn)
    assert result == sample


@pytest.mark.asyncio
async def test_config_success(monkeypatch):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/config"
        return httpx.Response(200, json={"version": "2026.4.1"})

    _install_transport(monkeypatch, handler)
    result = await config(conn)
    assert result["version"] == "2026.4.1"


@pytest.mark.asyncio
async def test_services_success(monkeypatch):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/services"
        return httpx.Response(
            200,
            json=[
                {"domain": "notify", "services": {"mobile_app_pixel9": {}}},
                {"domain": "light", "services": {"turn_on": {}}},
            ],
        )

    _install_transport(monkeypatch, handler)
    result = await services(conn)
    assert isinstance(result, list)
    assert result[0]["domain"] == "notify"


@pytest.mark.asyncio
async def test_call_notify_success(monkeypatch):
    conn = _make_conn()

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/services/notify/mobile_app_pixel9"
        captured["body"] = request.content
        return httpx.Response(200, json={})

    _install_transport(monkeypatch, handler)
    await call_notify(conn, "mobile_app_pixel9", {"title": "t", "message": "m"})
    assert b'"title":"t"' in captured["body"] or b'"title": "t"' in captured["body"]


# ── (b) auth errors: 401 and 403 → HAAuthError ─────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failures(monkeypatch, status):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "unauthorized"})

    _install_transport(monkeypatch, handler)
    with pytest.raises(HAAuthError):
        await ping(conn)


# ── (c) server errors + network failures → HAUnreachableError ───────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_5xx_unreachable(monkeypatch, status):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "server error"})

    _install_transport(monkeypatch, handler)
    with pytest.raises(HAUnreachableError):
        await ping(conn)


@pytest.mark.asyncio
async def test_connect_error_unreachable(monkeypatch):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    _install_transport(monkeypatch, handler)
    with pytest.raises(HAUnreachableError):
        await ping(conn)


@pytest.mark.asyncio
async def test_timeout_unreachable(monkeypatch):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _install_transport(monkeypatch, handler)
    with pytest.raises(HAUnreachableError):
        await ping(conn)


# ── (d) 200 with non-JSON → HAUnexpectedPayloadError ───────────────────


@pytest.mark.asyncio
async def test_non_json_200_unexpected_payload(monkeypatch):
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        # A reverse-proxy maintenance page is the canonical non-JSON 2xx.
        return httpx.Response(
            200,
            content=b"<html><body>Maintenance</body></html>",
            headers={"content-type": "text/html"},
        )

    _install_transport(monkeypatch, handler)
    with pytest.raises(HAUnexpectedPayloadError):
        await ping(conn)


# ── (e) Authorization header is always Bearer <token> ──────────────────


@pytest.mark.asyncio
async def test_bearer_token_header_on_every_call(monkeypatch):
    conn = _make_conn()
    seen_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json=[] if "states" in request.url.path else {})

    _install_transport(monkeypatch, handler)

    await ping(conn)
    await states(conn)
    await config(conn)
    await call_notify(conn, "mobile_app_pixel9", {"title": "t", "message": "m"})

    assert len(seen_headers) == 4
    for header in seen_headers:
        assert header == f"Bearer {TOKEN_PLAINTEXT}"


# ── (f) token plaintext never appears in logs ──────────────────────────


@pytest.mark.asyncio
async def test_token_never_leaks_into_logs(monkeypatch, caplog):
    """The client logs structured events on failure — none of them may
    carry the plaintext token, the ciphertext, or the encryption key."""
    conn = _make_conn()

    def handler(request: httpx.Request) -> httpx.Response:
        # Drive a classified failure that triggers the warning logs.
        return httpx.Response(500, json={"message": "boom"})

    _install_transport(monkeypatch, handler)

    with caplog.at_level(logging.DEBUG, logger="app.services.ha_client"):
        with pytest.raises(HAUnreachableError):
            await ping(conn)

    combined = "\n".join(rec.getMessage() for rec in caplog.records)
    combined += "\n".join(repr(rec.__dict__) for rec in caplog.records)
    assert TOKEN_PLAINTEXT not in combined
