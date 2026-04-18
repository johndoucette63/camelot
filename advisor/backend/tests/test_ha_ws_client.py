"""Tests for ha_ws_client — the HA WebSocket helper (feature 016 follow-up).

Uses a hand-rolled fake WebSocket with an async send/recv queue so we
exercise the real auth handshake + message handling without a live HA.
"""
from __future__ import annotations

import asyncio
import json
from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest
from websockets.exceptions import InvalidHandshake

from app.models.home_assistant_connection import HomeAssistantConnection
from app.security import encrypt_token
from app.services import ha_ws_client
from app.services.ha_ws_client import (
    HAWSAuthError,
    HAWSProtocolError,
    HAWSUnreachableError,
    discover_routers,
    list_thread_datasets,
)


# ── Fake WebSocket ─────────────────────────────────────────────────────


class _FakeWS:
    """Minimal stand-in for a websockets.WebSocketClientProtocol."""

    def __init__(self, scripted: list[str]) -> None:
        self._incoming = deque(scripted)
        self.sent: list[str] = []
        self.closed = False

    async def recv(self) -> str:
        if not self._incoming:
            # Simulate a long idle — the client uses wait_for() so this
            # should time out cleanly rather than hang the test.
            await asyncio.sleep(10)
            return "{}"
        return self._incoming.popleft()

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self):  # pragma: no cover — we don't use `async with`
        return self

    async def __aexit__(self, *a):  # pragma: no cover
        await self.close()


def _install_fake_connect(monkeypatch, fake_ws: _FakeWS) -> None:
    """Patch websockets.connect to return ``fake_ws`` immediately."""

    async def _fake_connect(*_args, **_kwargs):
        return fake_ws

    monkeypatch.setattr(ha_ws_client.websockets, "connect", _fake_connect)


def _conn() -> HomeAssistantConnection:
    return HomeAssistantConnection(
        id=1,
        base_url="http://homeassistant.local:8123",
        token_ciphertext=encrypt_token("test-token-abcd"),
    )


# ── list_thread_datasets ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_thread_datasets_happy_path(monkeypatch):
    ws = _FakeWS(
        [
            json.dumps({"type": "auth_required", "ha_version": "test"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps(
                {
                    "id": 1,
                    "type": "result",
                    "success": True,
                    "result": {
                        "datasets": [
                            {
                                "dataset_id": "d1",
                                "network_name": "MyHome",
                                "preferred": True,
                                "extended_pan_id": "11439b286af949e4",
                            },
                            {
                                "dataset_id": "d2",
                                "network_name": "AMZN-Thread",
                                "preferred": False,
                                "extended_pan_id": "f76e5ddbd899f376",
                            },
                        ]
                    },
                }
            ),
        ]
    )
    _install_fake_connect(monkeypatch, ws)

    result = await list_thread_datasets(_conn())

    assert len(result) == 2
    assert result[0]["network_name"] == "MyHome"
    assert result[0]["preferred"] is True
    # First send is the auth payload; second is the list_datasets command.
    sent = [json.loads(s) for s in ws.sent]
    assert sent[0] == {"type": "auth", "access_token": "test-token-abcd"}
    assert sent[1] == {"id": 1, "type": "thread/list_datasets"}


@pytest.mark.asyncio
async def test_auth_invalid_raises_auth_error(monkeypatch):
    ws = _FakeWS(
        [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_invalid", "message": "bad token"}),
        ]
    )
    _install_fake_connect(monkeypatch, ws)

    with pytest.raises(HAWSAuthError):
        await list_thread_datasets(_conn())


@pytest.mark.asyncio
async def test_unexpected_first_frame_raises_protocol_error(monkeypatch):
    ws = _FakeWS(
        [
            # Server sends something other than auth_required
            json.dumps({"type": "pong"}),
        ]
    )
    _install_fake_connect(monkeypatch, ws)

    with pytest.raises(HAWSProtocolError):
        await list_thread_datasets(_conn())


@pytest.mark.asyncio
async def test_connect_failure_maps_to_unreachable(monkeypatch):
    async def _raise_connect(*_a, **_kw):
        raise OSError("refused")

    monkeypatch.setattr(ha_ws_client.websockets, "connect", _raise_connect)

    with pytest.raises(HAWSUnreachableError):
        await list_thread_datasets(_conn())


@pytest.mark.asyncio
async def test_list_datasets_command_failure_raises_protocol_error(monkeypatch):
    ws = _FakeWS(
        [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps(
                {"id": 1, "type": "result", "success": False, "error": "nope"}
            ),
        ]
    )
    _install_fake_connect(monkeypatch, ws)

    with pytest.raises(HAWSProtocolError):
        await list_thread_datasets(_conn())


# ── discover_routers ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discover_routers_collects_events_and_unsubscribes(monkeypatch):
    """Subscription confirmation + two router_discovered events + idle."""
    ws = _FakeWS(
        [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            # subscription confirmation
            json.dumps({"id": 1, "type": "result", "success": True, "result": None}),
            # two router events
            json.dumps(
                {
                    "id": 1,
                    "type": "event",
                    "event": {
                        "type": "router_discovered",
                        "key": "aaaa",
                        "data": {
                            "extended_address": "aaaa",
                            "instance_name": "Man Cave",
                            "model_name": "BorderRouter",
                            "vendor_name": "Apple",
                            "network_name": "MyHome",
                            "extended_pan_id": "11439b286af949e4",
                            "addresses": ["192.168.10.101", "fd11::1"],
                            "server": "Man-Cave.local.",
                            "thread_version": "1.3.0",
                            "brand": "apple",
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "id": 1,
                    "type": "event",
                    "event": {
                        "type": "router_discovered",
                        "key": "bbbb",
                        "data": {
                            "extended_address": "bbbb",
                            "instance_name": "Aqara Hub",
                            "network_name": "MyHome",
                            "extended_pan_id": "11439b286af949e4",
                            "addresses": ["192.168.10.150"],
                        },
                    },
                }
            ),
        ]
    )
    _install_fake_connect(monkeypatch, ws)

    # Short duration so the test finishes fast — fake_ws.recv() will block
    # after the scripted messages are drained.
    routers = await discover_routers(_conn(), duration_seconds=0.3)

    assert len(routers) == 2
    assert routers[0]["extended_address"] == "aaaa"
    assert routers[0]["instance_name"] == "Man Cave"
    assert routers[1]["extended_address"] == "bbbb"

    # Client sent: auth, subscribe, unsubscribe (best effort).
    sent = [json.loads(s) for s in ws.sent]
    assert sent[0]["type"] == "auth"
    assert sent[1] == {"id": 1, "type": "thread/discover_routers"}
    assert any(
        s.get("type") == "unsubscribe_events" and s.get("subscription") == 1
        for s in sent
    )


@pytest.mark.asyncio
async def test_discover_routers_ignores_unknown_event_types(monkeypatch):
    ws = _FakeWS(
        [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({"id": 1, "type": "result", "success": True, "result": None}),
            json.dumps(
                {
                    "id": 1,
                    "type": "event",
                    "event": {"type": "something_else", "data": {}},
                }
            ),
            json.dumps(
                {
                    "id": 1,
                    "type": "event",
                    "event": {
                        "type": "router_discovered",
                        "data": {"extended_address": "cccc"},
                    },
                }
            ),
        ]
    )
    _install_fake_connect(monkeypatch, ws)

    routers = await discover_routers(_conn(), duration_seconds=0.3)

    assert len(routers) == 1
    assert routers[0]["extended_address"] == "cccc"


@pytest.mark.asyncio
async def test_discover_routers_failed_subscription(monkeypatch):
    ws = _FakeWS(
        [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({"id": 1, "type": "result", "success": False}),
        ]
    )
    _install_fake_connect(monkeypatch, ws)

    with pytest.raises(HAWSProtocolError):
        await discover_routers(_conn(), duration_seconds=0.3)


# ── URL translation ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "base,expected",
    [
        ("http://homeassistant.local:8123", "ws://homeassistant.local:8123/api/websocket"),
        ("https://ha.example.org", "wss://ha.example.org/api/websocket"),
        ("http://192.168.10.117:8123/", "ws://192.168.10.117:8123/api/websocket"),
    ],
)
def test_ws_url_translation(base, expected):
    conn = SimpleNamespace(base_url=base)
    assert ha_ws_client._ws_url(conn) == expected  # noqa: SLF001 — inspected internal
