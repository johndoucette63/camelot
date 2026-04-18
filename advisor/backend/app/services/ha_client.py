"""Home Assistant REST client (feature 016).

Thin async wrapper around ``httpx.AsyncClient`` for the subset of HA REST
endpoints the advisor needs: ``/api/``, ``/api/states``, ``/api/config``,
``/api/services``, and ``/api/services/notify/<service>``.

Each public method takes a ``HomeAssistantConnection`` row, decrypts the
stored token for the duration of the call only (never caches it across
calls), and raises one of four classified exceptions per research R8:

* ``HAAuthError``           — HTTP 401 / 403
* ``HAUnreachableError``    — connection errors, timeouts, 5xx
* ``HAUnexpectedPayloadError`` — 2xx with non-JSON or schema mismatch
* ``HAClientError``         — base class for the above

Successful 2xx responses are parsed as JSON and returned. Failure logs are
structured JSON; they NEVER include the token, its ciphertext, or the
encryption key.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import settings
from app.models.home_assistant_connection import HomeAssistantConnection
from app.security import TokenDecryptionError, decrypt_token

logger = logging.getLogger(__name__)


# ── Error classes (research R8) ──────────────────────────────────────────


class HAClientError(Exception):
    """Base class for classified HA REST errors.

    The ``error_class`` attribute is the short classification string used
    for the ``home_assistant_connections.last_error`` column and surfaced
    in the UI so the admin can fix the right thing.
    """

    error_class: str = "unknown"


class HAAuthError(HAClientError):
    error_class = "auth_failure"


class HAUnreachableError(HAClientError):
    error_class = "unreachable"


class HAUnexpectedPayloadError(HAClientError):
    error_class = "unexpected_payload"


# ── Internal helpers ─────────────────────────────────────────────────────


def _base_url(conn: HomeAssistantConnection) -> str:
    """Return a normalised base URL with no trailing slash."""
    if not conn.base_url:
        raise HAUnreachableError("Home Assistant connection has no base URL configured")
    return conn.base_url.rstrip("/")


def _headers(conn: HomeAssistantConnection) -> dict[str, str]:
    """Return HA REST headers with a freshly-decrypted bearer token.

    The decrypted token exists only as a local variable for the lifetime
    of a single call — it is never stored on ``conn`` or cached at the
    module level.
    """
    if conn.token_ciphertext is None:
        raise HAAuthError("Home Assistant connection has no stored token")
    try:
        token = decrypt_token(conn.token_ciphertext)
    except TokenDecryptionError as exc:
        # Operator-visible as an auth failure — the DB ciphertext can't be
        # unlocked with the current ADVISOR_ENCRYPTION_KEY. The admin must
        # re-save the connection in Settings.
        raise HAAuthError(str(exc)) from exc
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _classify_response(resp: httpx.Response, method: str, path: str) -> None:
    """Raise the appropriate HAClientError for a non-2xx response."""
    status = resp.status_code
    if status in (401, 403):
        logger.warning(
            "ha_client.auth_failure",
            extra={
                "event": "ha_client.auth_failure",
                "method": method,
                "path": path,
                "status_code": status,
            },
        )
        raise HAAuthError(
            f"Home Assistant rejected the token (HTTP {status})."
        )
    if status >= 500:
        logger.warning(
            "ha_client.server_error",
            extra={
                "event": "ha_client.server_error",
                "method": method,
                "path": path,
                "status_code": status,
            },
        )
        raise HAUnreachableError(
            f"Home Assistant returned HTTP {status} (server error)."
        )
    if status >= 400:
        # 4xx that isn't 401/403 — surface as unexpected payload rather than
        # lying about the cause. Rare in practice (HA REST is very stable).
        logger.warning(
            "ha_client.client_error",
            extra={
                "event": "ha_client.client_error",
                "method": method,
                "path": path,
                "status_code": status,
            },
        )
        raise HAUnexpectedPayloadError(
            f"Home Assistant returned HTTP {status}."
        )


def _parse_json(resp: httpx.Response, method: str, path: str) -> Any:
    """Parse a 2xx response as JSON or raise HAUnexpectedPayloadError."""
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "ha_client.unexpected_payload",
            extra={
                "event": "ha_client.unexpected_payload",
                "method": method,
                "path": path,
                "status_code": resp.status_code,
                "error": str(exc),
            },
        )
        raise HAUnexpectedPayloadError(
            "Home Assistant returned a non-JSON response. Check the base URL."
        ) from exc


async def _request(
    conn: HomeAssistantConnection,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
) -> Any:
    """Shared request helper — decrypt token, classify errors, parse JSON."""
    url = f"{_base_url(conn)}{path}"
    headers = _headers(conn)
    timeout = float(settings.ha_request_timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers, json=json_body)
    except httpx.TimeoutException as exc:
        logger.warning(
            "ha_client.timeout",
            extra={
                "event": "ha_client.timeout",
                "method": method,
                "path": path,
                "timeout_s": timeout,
            },
        )
        raise HAUnreachableError(f"Home Assistant request timed out after {timeout}s") from exc
    except httpx.RequestError as exc:
        logger.warning(
            "ha_client.request_error",
            extra={
                "event": "ha_client.request_error",
                "method": method,
                "path": path,
                "error": str(exc),
            },
        )
        raise HAUnreachableError(f"Home Assistant is unreachable: {exc}") from exc

    _classify_response(resp, method, path)
    return _parse_json(resp, method, path)


# ── Public API ───────────────────────────────────────────────────────────


async def ping(conn: HomeAssistantConnection) -> dict[str, Any]:
    """Hit ``GET /api/`` — the canonical HA reachability probe."""
    return await _request(conn, "GET", "/api/")


async def states(conn: HomeAssistantConnection) -> list[dict[str, Any]]:
    """``GET /api/states`` — full state list for the filter pipeline."""
    result = await _request(conn, "GET", "/api/states")
    if not isinstance(result, list):
        raise HAUnexpectedPayloadError(
            "Home Assistant /api/states returned a non-list payload."
        )
    return result


async def config(conn: HomeAssistantConnection) -> dict[str, Any]:
    """``GET /api/config`` — HA core version + location metadata."""
    return await _request(conn, "GET", "/api/config")


async def services(conn: HomeAssistantConnection) -> list[dict[str, Any]]:
    """``GET /api/services`` — used to populate notify-service pickers."""
    result = await _request(conn, "GET", "/api/services")
    if not isinstance(result, list):
        raise HAUnexpectedPayloadError(
            "Home Assistant /api/services returned a non-list payload."
        )
    return result


async def call_notify(
    conn: HomeAssistantConnection,
    service: str,
    payload: dict[str, Any],
) -> Any:
    """``POST /api/services/notify/<service>`` — fire a notify service call.

    The caller supplies the bare service suffix (e.g. ``mobile_app_pixel9``)
    without the ``notify.`` prefix, matching how the name is stored in
    ``notification_sinks.endpoint``. If the caller accidentally includes
    the prefix, strip it so the URL is well-formed either way.
    """
    suffix = service[len("notify."):] if service.startswith("notify.") else service
    return await _request(
        conn, "POST", f"/api/services/notify/{suffix}", json_body=payload
    )


async def device_registry_map(
    conn: HomeAssistantConnection,
) -> dict[str, str]:
    """Return a ``{entity_id: ha_device_id}`` map for every entity HA knows.

    ``/api/states`` deliberately does NOT include ``device_id`` in entity
    attributes (device identity lives in HA's device registry, which REST
    exposes only through ``/api/template`` or the WebSocket API). We issue
    one template render per poll cycle that walks ``states`` and emits a
    JSON list of ``[entity_id, device_id]`` pairs for every entity where
    the ``device_id()`` Jinja function returns a non-null UUID. Entities
    that belong to no device registry entry (helpers, manually-created
    templates, etc.) are omitted — callers synthesize a fallback
    ``ha_device_id`` for them so they still land in the snapshot.
    """
    template = (
        "{% set ns = namespace(items=[]) %}"
        "{% for s in states %}"
        "{% set did = device_id(s.entity_id) %}"
        "{% if did %}"
        "{% set ns.items = ns.items + [[s.entity_id, did]] %}"
        "{% endif %}"
        "{% endfor %}"
        "{{ ns.items | tojson }}"
    )
    result = await _request(
        conn, "POST", "/api/template", json_body={"template": template}
    )
    if not isinstance(result, list):
        raise HAUnexpectedPayloadError(
            "Home Assistant /api/template returned an unexpected shape for the device registry map."
        )
    return {
        pair[0]: str(pair[1])
        for pair in result
        if isinstance(pair, list) and len(pair) == 2 and pair[0] and pair[1]
    }


async def list_notify_services(conn: HomeAssistantConnection) -> list[str]:
    """Return every ``notify.*`` service name exposed by this HA instance.

    Calls ``GET /api/services`` and filters to entries whose ``domain``
    is ``notify``. HA's ``/api/services`` returns a list of
    ``{"domain": "...", "services": {"<service_name>": {...}, ...}}``
    dicts. We return the list of service names (dict keys) WITHOUT the
    ``notify.`` prefix so the names match the canonical form stored in
    ``notification_sinks.endpoint`` (research T054 canonical naming).

    Propagates the same classified exceptions as ``services()`` —
    ``HAAuthError``, ``HAUnreachableError``, ``HAUnexpectedPayloadError``.
    Callers in the settings UI map those to a 409 response.
    """
    raw = await services(conn)
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("domain") != "notify":
            continue
        svcs = entry.get("services") or {}
        if isinstance(svcs, dict):
            # Preserve HA's dict ordering so the UI's dropdown stays
            # predictable across reloads.
            names.extend(str(k) for k in svcs.keys())
        elif isinstance(svcs, list):
            # Defensive: some HA builds emit a list of service records.
            for s in svcs:
                if isinstance(s, dict):
                    n = s.get("service") or s.get("name")
                    if n:
                        names.append(str(n))
    return names


async def thread_status(conn: HomeAssistantConnection) -> dict[str, Any] | None:
    """``GET /api/config/thread/status`` — the Thread diagnostic blob (R3).

    Returns ``None`` when HA has no Thread integration configured — the
    endpoint answers with 404 or 501 in that case, which is a legitimate
    empty-state the poller must handle without raising (FR-013).

    All other failure modes (auth, unreachable, unexpected payload) raise
    the same classified exceptions as the other public methods so the
    poller can record them on the connection row.
    """
    path = "/api/config/thread/status"
    url = f"{_base_url(conn)}{path}"
    headers = _headers(conn)
    timeout = float(settings.ha_request_timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException as exc:
        logger.warning(
            "ha_client.timeout",
            extra={
                "event": "ha_client.timeout",
                "method": "GET",
                "path": path,
                "timeout_s": timeout,
            },
        )
        raise HAUnreachableError(
            f"Home Assistant request timed out after {timeout}s"
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "ha_client.request_error",
            extra={
                "event": "ha_client.request_error",
                "method": "GET",
                "path": path,
                "error": str(exc),
            },
        )
        raise HAUnreachableError(f"Home Assistant is unreachable: {exc}") from exc

    # 404 / 501 mean "this HA instance has no Thread integration". Return
    # None so the caller can truncate the Thread tables without flagging an
    # error on the connection row.
    if resp.status_code in (404, 501):
        return None

    _classify_response(resp, "GET", path)
    payload = _parse_json(resp, "GET", path)
    if not isinstance(payload, dict):
        raise HAUnexpectedPayloadError(
            "Home Assistant /api/config/thread/status returned a non-object payload."
        )
    return payload
