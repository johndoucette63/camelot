"""Home Assistant WebSocket client — feature 016, follow-up to research R3.

HA's Thread topology is not exposed via REST. ``/api/config/thread/status``
returns 404 on current HA versions (the path either never existed or was
removed). The HA frontend reads Thread data via the authenticated
WebSocket API at ``/api/websocket``, specifically:

* ``thread/list_datasets`` — one-shot request/response listing every Thread
  network HA knows about, with a ``preferred`` flag.
* ``thread/discover_routers`` — a subscription that emits
  ``router_discovered`` events via mDNS as HA finds each border router on
  the LAN. We subscribe for a short window, collect events, unsubscribe.

This module exposes thin request-response helpers used by ``ha_poller``.
Connections are per-call (open, authenticate, do one thing, close) — the
poll cycle runs once a minute, so connection overhead is negligible and
we avoid long-lived connection state (reconnect, ping/pong) entirely.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosed, InvalidHandshake, WebSocketException

from app.config import settings
from app.models.home_assistant_connection import HomeAssistantConnection
from app.security import decrypt_token

logger = logging.getLogger(__name__)


class HAWSError(Exception):
    """Base class for HA WebSocket errors. ``error_class`` mirrors the REST
    classification used by ``ha_client`` so the poller can route both paths
    through the same connection-health recording."""

    error_class: str = "unreachable"


class HAWSAuthError(HAWSError):
    error_class = "auth_failure"


class HAWSUnreachableError(HAWSError):
    error_class = "unreachable"


class HAWSProtocolError(HAWSError):
    """Unexpected message shape — not auth, not a network failure."""

    error_class = "unexpected_payload"


def _ws_url(conn: HomeAssistantConnection) -> str:
    """Translate the stored REST base URL into the ``ws://``/``wss://`` form."""
    base = (conn.base_url or "").rstrip("/")
    if base.startswith("https://"):
        return base.replace("https://", "wss://", 1) + "/api/websocket"
    return base.replace("http://", "ws://", 1) + "/api/websocket"


@asynccontextmanager
async def _connect(
    conn: HomeAssistantConnection,
) -> AsyncIterator[Any]:
    """Open an authenticated WebSocket, yield it, close on exit.

    The handshake per HA docs:
      1. server sends ``auth_required``
      2. client sends ``auth`` with the access token
      3. server sends ``auth_ok`` (or ``auth_invalid``)
    """
    url = _ws_url(conn)
    try:
        token = decrypt_token(conn.token_ciphertext or b"")
    except Exception as exc:
        raise HAWSAuthError(f"Cannot decrypt stored HA token: {exc}") from exc

    timeout = float(settings.ha_request_timeout_seconds)
    try:
        ws = await asyncio.wait_for(
            websockets.connect(
                url,
                open_timeout=timeout,
                close_timeout=2.0,
                max_size=4 * 1024 * 1024,  # 4MB — Thread payloads are small, but be generous
            ),
            timeout=timeout,
        )
    except (OSError, InvalidHandshake, asyncio.TimeoutError, WebSocketException) as exc:
        raise HAWSUnreachableError(f"Cannot open WS to {url}: {exc}") from exc

    try:
        # Handshake message 1: auth_required
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except (asyncio.TimeoutError, ConnectionClosed) as exc:
            raise HAWSUnreachableError("Timed out waiting for auth_required") from exc
        msg = _parse(raw)
        if msg.get("type") != "auth_required":
            raise HAWSProtocolError(
                f"Expected auth_required, got type={msg.get('type')!r}"
            )

        await ws.send(json.dumps({"type": "auth", "access_token": token}))

        # Handshake message 2: auth_ok or auth_invalid
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except (asyncio.TimeoutError, ConnectionClosed) as exc:
            raise HAWSUnreachableError("Timed out waiting for auth_ok") from exc
        msg = _parse(raw)
        if msg.get("type") == "auth_invalid":
            raise HAWSAuthError(
                f"HA rejected access token: {msg.get('message', 'auth_invalid')}"
            )
        if msg.get("type") != "auth_ok":
            raise HAWSProtocolError(
                f"Expected auth_ok, got type={msg.get('type')!r}"
            )

        yield ws
    finally:
        try:
            await asyncio.wait_for(ws.close(), timeout=2.0)
        except Exception:  # noqa: BLE001 — best-effort close
            pass


def _parse(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HAWSProtocolError(f"Invalid JSON frame: {exc}") from exc
    if not isinstance(msg, dict):
        raise HAWSProtocolError(f"Expected dict frame, got {type(msg).__name__}")
    return msg


async def list_thread_datasets(
    conn: HomeAssistantConnection,
) -> list[dict[str, Any]]:
    """Return every Thread network HA knows about.

    Each dataset dict includes ``dataset_id``, ``network_name``,
    ``extended_pan_id``, ``pan_id``, ``channel``, and a ``preferred`` bool.
    """
    async with _connect(conn) as ws:
        await ws.send(json.dumps({"id": 1, "type": "thread/list_datasets"}))
        try:
            raw = await asyncio.wait_for(
                ws.recv(), timeout=float(settings.ha_request_timeout_seconds)
            )
        except (asyncio.TimeoutError, ConnectionClosed) as exc:
            raise HAWSUnreachableError("Timed out waiting for list_datasets reply") from exc
        msg = _parse(raw)
        if msg.get("type") != "result" or not msg.get("success"):
            raise HAWSProtocolError(f"list_datasets failed: {msg}")
        result = msg.get("result") or {}
        return list(result.get("datasets") or [])


async def discover_routers(
    conn: HomeAssistantConnection,
    duration_seconds: float = 3.5,
) -> list[dict[str, Any]]:
    """Subscribe to ``thread/discover_routers``, collect mDNS-discovered
    border routers for ``duration_seconds``, unsubscribe, return the list.

    Each router dict has (at least): ``extended_address`` (stable id),
    ``instance_name``, ``model_name``, ``vendor_name``, ``network_name``,
    ``extended_pan_id``, ``addresses`` (list of IPs including LAN IPv4),
    ``server`` (mDNS hostname), ``thread_version``, ``brand``.
    """
    routers: list[dict[str, Any]] = []
    sub_id = 1
    async with _connect(conn) as ws:
        await ws.send(json.dumps({"id": sub_id, "type": "thread/discover_routers"}))

        # First message is either the subscription-confirmation result, or
        # (if HA has cached routers) a router_discovered event. Collect
        # both shapes until the window closes.
        loop = asyncio.get_event_loop()
        deadline = loop.time() + duration_seconds
        subscribed = False

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            except ConnectionClosed as exc:
                raise HAWSUnreachableError(f"WS closed mid-discover: {exc}") from exc

            msg = _parse(raw)
            mtype = msg.get("type")
            if mtype == "result":
                if not msg.get("success"):
                    raise HAWSProtocolError(f"discover_routers failed: {msg}")
                subscribed = True
                continue
            if mtype == "event":
                event = msg.get("event") or {}
                if event.get("type") == "router_discovered":
                    data = event.get("data")
                    if isinstance(data, dict):
                        routers.append(data)

        # Best-effort unsubscribe (HA cleans up on close anyway).
        if subscribed:
            try:
                await asyncio.wait_for(
                    ws.send(
                        json.dumps(
                            {
                                "id": sub_id + 1,
                                "type": "unsubscribe_events",
                                "subscription": sub_id,
                            }
                        )
                    ),
                    timeout=2.0,
                )
            except Exception:  # noqa: BLE001 — connection will close anyway
                pass

    return routers
