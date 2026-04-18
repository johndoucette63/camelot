"""Settings endpoints — thresholds, mutes, notification sinks, HA connection."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database import async_session
from app.models.alert_threshold import AlertThreshold
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.notification_sink import NotificationSink
from app.models.rule_mute import RuleMute
from app.schemas.home_assistant import (
    HAConnectionRead,
    HAConnectionStatus,
    HAConnectionUpsert,
)
from app.security import (
    TokenDecryptionError,
    decrypt_token,
    encrypt_token,
    mask_token,
)
from app.services import ha_client, ha_inventory_merge, notification_sender
from app.services.ha_client import (
    HAAuthError,
    HAClientError,
    HAUnexpectedPayloadError,
    HAUnreachableError,
)
from app.services.rules import RULES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

_RULE_NAME_BY_ID = {rule.id: rule.name for rule in RULES}
MAX_MUTE_SECONDS = 86400 * 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _serialize_threshold(row: AlertThreshold) -> dict[str, Any]:
    return {
        "key": row.key,
        "value": float(row.value),
        "unit": row.unit,
        "default_value": float(row.default_value),
        "min_value": float(row.min_value),
        "max_value": float(row.max_value),
        "updated_at": _iso(row.updated_at),
    }


async def _target_label(session, target_type: str, target_id: int | None) -> str | None:
    if target_id is None:
        return None
    if target_type == "device":
        from app.models.device import Device

        row = await session.get(Device, target_id)
        return row.hostname or row.ip_address if row else None
    if target_type == "service":
        from app.models.service_definition import ServiceDefinition

        row = await session.get(ServiceDefinition, target_id)
        return f"{row.name} ({row.host_label})" if row else None
    return None


def _serialize_mute(mute: RuleMute, target_label: str | None, now: datetime) -> dict[str, Any]:
    remaining = max(int((mute.expires_at - now).total_seconds()), 0)
    return {
        "id": mute.id,
        "rule_id": mute.rule_id,
        "rule_name": _RULE_NAME_BY_ID.get(mute.rule_id.split(":", 1)[0], mute.rule_id),
        "target_type": mute.target_type,
        "target_id": mute.target_id,
        "target_label": target_label,
        "created_at": _iso(mute.created_at),
        "expires_at": _iso(mute.expires_at),
        "remaining_seconds": remaining,
        "note": mute.note,
    }


# ── Thresholds ──────────────────────────────────────────────────────────


@router.get("/thresholds")
async def list_thresholds() -> dict[str, Any]:
    async with async_session() as session:
        rows = (await session.execute(select(AlertThreshold).order_by(AlertThreshold.key))).scalars().all()
    return {"thresholds": [_serialize_threshold(r) for r in rows]}


class ThresholdUpdate(BaseModel):
    value: float


@router.put("/thresholds/{key}")
async def update_threshold(key: str, body: ThresholdUpdate) -> dict[str, Any]:
    async with async_session() as session:
        row = await session.get(AlertThreshold, key)
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown threshold '{key}'")

        try:
            new_value = Decimal(str(body.value))
        except InvalidOperation:
            raise HTTPException(status_code=400, detail="value must be numeric")

        if new_value < row.min_value or new_value > row.max_value:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"value must be between {float(row.min_value)} "
                    f"and {float(row.max_value)}"
                ),
            )

        row.value = new_value
        row.updated_at = _utcnow()
        await session.commit()
        await session.refresh(row)
        return _serialize_threshold(row)


# ── Mutes ───────────────────────────────────────────────────────────────


@router.get("/mutes")
async def list_mutes(include_expired: bool = Query(False)) -> dict[str, Any]:
    now = _utcnow()
    async with async_session() as session:
        q = select(RuleMute).order_by(RuleMute.created_at.desc())
        if not include_expired:
            q = q.where(RuleMute.cancelled_at.is_(None), RuleMute.expires_at > now)
        rows = (await session.execute(q)).scalars().all()

        mutes = []
        for row in rows:
            label = await _target_label(session, row.target_type, row.target_id)
            mutes.append(_serialize_mute(row, label, now))
    return {"mutes": mutes}


class MuteCreate(BaseModel):
    rule_id: str
    target_type: Literal["device", "service", "system"]
    target_id: int | None = None
    duration_seconds: int = Field(..., gt=0)
    note: str | None = None


@router.post("/mutes", status_code=201)
async def create_mute(body: MuteCreate) -> dict[str, Any]:
    if body.duration_seconds > MAX_MUTE_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"duration must be ≤ {MAX_MUTE_SECONDS} seconds (7 days)",
        )

    if body.target_type == "system":
        if body.target_id is not None:
            raise HTTPException(
                status_code=400, detail="target_id must be null for target_type='system'"
            )
    else:
        if body.target_id is None:
            raise HTTPException(
                status_code=400,
                detail=f"target_id is required for target_type='{body.target_type}'",
            )

    # Validate rule_id exists (allow prefix match for unknown_device:MAC form)
    base_id = body.rule_id.split(":", 1)[0]
    if base_id not in _RULE_NAME_BY_ID:
        raise HTTPException(status_code=400, detail=f"unknown rule_id '{body.rule_id}'")

    if body.note is not None and len(body.note) > 500:
        raise HTTPException(status_code=400, detail="note must be ≤ 500 characters")

    now = _utcnow()
    mute = RuleMute(
        rule_id=body.rule_id,
        target_type=body.target_type,
        target_id=body.target_id,
        created_at=now,
        expires_at=now + timedelta(seconds=body.duration_seconds),
        note=body.note,
    )
    async with async_session() as session:
        session.add(mute)
        await session.commit()
        await session.refresh(mute)
        label = await _target_label(session, mute.target_type, mute.target_id)
        return _serialize_mute(mute, label, now)


@router.delete("/mutes/{mute_id}", status_code=204)
async def cancel_mute(mute_id: int):
    async with async_session() as session:
        row = await session.get(RuleMute, mute_id)
        if row is None:
            return Response(status_code=204)
        if row.cancelled_at is None:
            row.cancelled_at = _utcnow()
            await session.commit()
    return Response(status_code=204)


# ── Notification sinks ──────────────────────────────────────────────────

_WEBHOOK_PATH_RE = re.compile(r"(/api/webhook/)([^/?]+)")


def mask_endpoint(url: str) -> str:
    """Replace webhook tokens and query-string secrets with ``***``.

    Matches `/api/webhook/<token>` in the path and any query string (the
    whole query is redacted, since tokens may be there under any name).
    """
    masked = _WEBHOOK_PATH_RE.sub(r"\1***", url)
    parsed = urlparse(masked)
    if parsed.query:
        parsed = parsed._replace(query="***")
    return urlunparse(parsed)


def _serialize_sink(sink: NotificationSink) -> dict[str, Any]:
    return {
        "id": sink.id,
        "type": sink.type,
        "name": sink.name,
        "enabled": sink.enabled,
        "endpoint_masked": mask_endpoint(sink.endpoint),
        "min_severity": sink.min_severity,
        "created_at": _iso(sink.created_at),
        "updated_at": _iso(sink.updated_at),
    }


class SinkCreate(BaseModel):
    """Create a new notification sink.

    Two shapes coexist for backward compatibility:

    * **Webhook-into-HA** (F4.5/011): ``type="home_assistant"``,
      ``endpoint`` is an ``http(s)://...`` URL for an HA
      ``/api/webhook/<id>`` endpoint. Historically this is what we
      called "Home Assistant notifications" in the UI.
    * **HA-native notify** (feature 016 / US-3): ``type="home_assistant"``,
      ``endpoint`` is a bare notify-service suffix such as
      ``mobile_app_pixel9`` (the ``notify.`` prefix is stripped at ingest
      if the admin includes it). Requires a configured HA connection
      (``PUT /settings/home-assistant`` must have succeeded first);
      the server then resolves the HA base URL + bearer token from
      the singleton connection row and links the sink via
      ``home_assistant_id = 1``.

    The two shapes are distinguished by whether ``endpoint`` contains
    ``://`` — URLs are routed to the legacy webhook path, bare suffixes
    are routed to the HA-native notify path. ``endpoint`` is therefore
    a ``str`` rather than ``AnyHttpUrl`` so both shapes validate.
    """

    type: Literal["home_assistant"] = "home_assistant"
    name: str
    enabled: bool = False
    endpoint: str
    min_severity: Literal["info", "warning", "critical"] = "critical"


class SinkUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    endpoint: str | None = None
    min_severity: Literal["info", "warning", "critical"] | None = None


@router.get("/notifications")
async def list_sinks() -> dict[str, Any]:
    async with async_session() as session:
        rows = (
            (await session.execute(select(NotificationSink).order_by(NotificationSink.id)))
            .scalars()
            .all()
        )
    return {"sinks": [_serialize_sink(r) for r in rows]}


def _canonical_notify_service(raw: str) -> str:
    """Strip a leading ``notify.`` prefix and surrounding whitespace.

    The canonical form stored in ``notification_sinks.endpoint`` is the
    bare suffix (``mobile_app_pixel9``), never the dotted full name
    (``notify.mobile_app_pixel9``). HA's ``call_notify`` helper
    reconstructs the full URL path as needed.
    """
    s = (raw or "").strip()
    if s.startswith("notify."):
        s = s[len("notify."):]
    return s


def _is_webhook_endpoint(endpoint: str) -> bool:
    return "://" in (endpoint or "")


@router.post("/notifications", status_code=201)
async def create_sink(body: SinkCreate) -> dict[str, Any]:
    async with async_session() as session:
        ha_id: int | None = None
        stored_endpoint = body.endpoint.strip()

        if not _is_webhook_endpoint(stored_endpoint):
            # HA-native notify path — require a configured HA connection.
            conn = await session.get(
                HomeAssistantConnection, HA_SINGLETON_ID
            )
            if conn is None or conn.base_url is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No Home Assistant connection configured. Save a "
                        "connection in Settings → Home Assistant first."
                    ),
                )
            # Canonical naming — strip any leading notify. prefix.
            stored_endpoint = _canonical_notify_service(stored_endpoint)
            if not stored_endpoint:
                raise HTTPException(
                    status_code=400,
                    detail="Notify service suffix is required.",
                )
            ha_id = conn.id

        sink = NotificationSink(
            type=body.type,
            name=body.name,
            enabled=body.enabled,
            endpoint=stored_endpoint,
            min_severity=body.min_severity,
            home_assistant_id=ha_id,
        )
        session.add(sink)
        await session.commit()
        await session.refresh(sink)
        return _serialize_sink(sink)


@router.put("/notifications/{sink_id}")
async def update_sink(sink_id: int, body: SinkUpdate) -> dict[str, Any]:
    async with async_session() as session:
        sink = await session.get(NotificationSink, sink_id)
        if sink is None:
            raise HTTPException(status_code=404, detail="sink not found")

        if body.name is not None:
            sink.name = body.name
        if body.enabled is not None:
            sink.enabled = body.enabled
        if body.min_severity is not None:
            sink.min_severity = body.min_severity
        if body.endpoint is not None:
            ep = body.endpoint.strip()
            if _is_webhook_endpoint(ep):
                sink.endpoint = ep
                sink.home_assistant_id = None
            else:
                conn = await session.get(
                    HomeAssistantConnection, HA_SINGLETON_ID
                )
                if conn is None or conn.base_url is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "No Home Assistant connection configured. Save "
                            "a connection in Settings → Home Assistant first."
                        ),
                    )
                canonical = _canonical_notify_service(ep)
                if not canonical:
                    raise HTTPException(
                        status_code=400,
                        detail="Notify service suffix is required.",
                    )
                sink.endpoint = canonical
                sink.home_assistant_id = conn.id
        sink.updated_at = _utcnow()

        await session.commit()
        await session.refresh(sink)
        return _serialize_sink(sink)


@router.delete("/notifications/{sink_id}", status_code=204)
async def delete_sink(sink_id: int):
    async with async_session() as session:
        sink = await session.get(NotificationSink, sink_id)
        if sink is None:
            return Response(status_code=204)
        await session.delete(sink)
        await session.commit()
    return Response(status_code=204)


@router.post("/notifications/{sink_id}/test")
async def test_sink(sink_id: int) -> Response:
    async with async_session() as session:
        sink = await session.get(NotificationSink, sink_id)
        if sink is None:
            raise HTTPException(status_code=404, detail="sink not found")
        result = await notification_sender.send_test(sink)

    status = 200 if result.get("ok") else 502
    return JSONResponse(status_code=status, content=result)


@router.get("/notifications/available-ha-services")
async def list_available_ha_services() -> Response:
    """Return ``notify.*`` service names available on the configured HA.

    Used by the Settings UI to populate the HA-sink service picker. On
    HA unreachable / auth failure / unexpected payload the endpoint
    returns 409 so the UI can fall back to free-text entry. A missing
    connection is also 409 — the UI copy distinguishes the two cases
    via the ``detail`` string.
    """
    async with async_session() as session:
        conn = await session.get(HomeAssistantConnection, HA_SINGLETON_ID)

    if conn is None or conn.base_url is None:
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "No Home Assistant connection configured. Save a "
                    "connection in Settings → Home Assistant first."
                )
            },
        )

    try:
        names = await ha_client.list_notify_services(conn)
    except HAClientError as exc:
        logger.warning(
            "ha_settings.list_notify_services.failed",
            extra={
                "event": "ha_settings.list_notify_services.failed",
                "status": _classify_exc(exc),
                "error": str(exc),
            },
        )
        return JSONResponse(
            status_code=409,
            content={"detail": "Home Assistant is not currently reachable"},
        )

    # Canonicalise — strip accidental notify. prefixes if any leaked
    # through HA's response (defensive; list_notify_services already
    # returns bare suffixes).
    services_out = [_canonical_notify_service(n) for n in names if n]
    return JSONResponse(
        status_code=200, content={"services": services_out}
    )


# ── Home Assistant connection (feature 016) ─────────────────────────────
#
# Contract: specs/016-ha-integration/contracts/home-assistant-api.md §1.
# The connection is a singleton row at id=1 managed in code (no delete —
# "deleted" == all configurable columns nulled so FKs from notification
# sinks stay valid).
#
# SECURITY: the plaintext access token is never logged, echoed, or
# serialised to the browser. Only ``mask_token(...)`` ever leaves this
# module via the API layer.


HA_SINGLETON_ID = 1


def _status_from_row(conn: HomeAssistantConnection | None) -> HAConnectionStatus:
    if conn is None or conn.base_url is None:
        return "not_configured"
    if conn.last_error:
        last = conn.last_error
        if last in ("auth_failure", "unreachable", "unexpected_payload"):
            return last  # type: ignore[return-value]
        return "unreachable"
    return "ok"


def _validate_base_url(base_url: str) -> str:
    url = base_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="base_url is required")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=400,
            detail="base_url must start with http:// or https://",
        )
    # Normalise trailing slashes so downstream code doesn't double-slash.
    return url.rstrip("/")


def _read_response(conn: HomeAssistantConnection | None) -> HAConnectionRead:
    """Build the redacted read-back for GET/PUT responses.

    Masks the token via a single local ``decrypt_token`` call whose
    plaintext is immediately fed to ``mask_token`` and discarded. The
    plaintext never leaves this function.
    """
    if conn is None or conn.base_url is None:
        return HAConnectionRead(configured=False, status="not_configured")

    token_masked: str | None = None
    status = _status_from_row(conn)
    last_error = conn.last_error

    if conn.token_ciphertext is not None:
        try:
            plaintext = decrypt_token(conn.token_ciphertext)
        except TokenDecryptionError as exc:
            status = "auth_failure"
            last_error = str(exc)
        else:
            token_masked = mask_token(plaintext)

    return HAConnectionRead(
        configured=True,
        base_url=conn.base_url,
        token_masked=token_masked,
        status=status,
        last_success_at=conn.last_success_at,
        last_error=last_error,
        last_error_at=conn.last_error_at,
    )


def _classify_exc(exc: HAClientError) -> str:
    """Map a client exception to the contract's status string."""
    if isinstance(exc, HAAuthError):
        return "auth_failure"
    if isinstance(exc, HAUnreachableError):
        return "unreachable"
    if isinstance(exc, HAUnexpectedPayloadError):
        return "unexpected_payload"
    return "unreachable"


async def _validate_with_ping(base_url: str, access_token: str) -> HAClientError | None:
    """Run a ``/api/`` probe against the supplied credentials.

    The probe uses a temporary in-memory ``HomeAssistantConnection`` object
    carrying the freshly-encrypted token; nothing is persisted. Returns
    ``None`` on success, or the classified exception on failure.
    """
    tmp_conn = HomeAssistantConnection(
        id=HA_SINGLETON_ID,
        base_url=base_url,
        token_ciphertext=encrypt_token(access_token),
    )
    try:
        await ha_client.ping(tmp_conn)
    except HAClientError as exc:
        return exc
    return None


@router.get("/home-assistant", response_model=HAConnectionRead)
async def get_home_assistant_connection() -> HAConnectionRead:
    async with async_session() as session:
        conn = await session.get(HomeAssistantConnection, HA_SINGLETON_ID)
        return _read_response(conn)


@router.put("/home-assistant")
async def upsert_home_assistant_connection(body: HAConnectionUpsert) -> Response:
    base_url = _validate_base_url(body.base_url)

    probe_error = await _validate_with_ping(base_url, body.access_token)
    if probe_error is not None:
        status_cls = _classify_exc(probe_error)
        logger.warning(
            "ha_settings.upsert.validation_failed",
            extra={
                "event": "ha_settings.upsert.validation_failed",
                "status": status_cls,
            },
        )
        return JSONResponse(
            status_code=400,
            content={"status": status_cls, "detail": str(probe_error)},
        )

    ciphertext = encrypt_token(body.access_token)
    now = _utcnow()

    async with async_session() as session:
        conn = await session.get(HomeAssistantConnection, HA_SINGLETON_ID)
        if conn is None:
            conn = HomeAssistantConnection(id=HA_SINGLETON_ID)
            session.add(conn)
        conn.base_url = base_url
        conn.token_ciphertext = ciphertext
        conn.last_success_at = now
        conn.last_error = None
        conn.last_error_at = None
        await session.commit()
        await session.refresh(conn)
        body_out = _read_response(conn).model_dump(mode="json")

    logger.info(
        "ha_settings.upsert.ok",
        extra={"event": "ha_settings.upsert.ok", "base_url": base_url},
    )
    return JSONResponse(status_code=200, content=body_out)


@router.post("/home-assistant/test-connection")
async def test_home_assistant_connection(body: HAConnectionUpsert) -> Response:
    base_url = _validate_base_url(body.base_url)
    probe_error = await _validate_with_ping(base_url, body.access_token)
    if probe_error is not None:
        status_cls = _classify_exc(probe_error)
        return JSONResponse(
            status_code=400,
            content={"status": status_cls, "detail": str(probe_error)},
        )
    # Success path — return the same shape as a GET would, but with the
    # values from the temporary validation (nothing persisted).
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "detail": "Home Assistant reachable."},
    )


@router.delete("/home-assistant", status_code=204)
async def delete_home_assistant_connection() -> Response:
    async with async_session() as session:
        conn = await session.get(HomeAssistantConnection, HA_SINGLETON_ID)
        if conn is None:
            conn = HomeAssistantConnection(id=HA_SINGLETON_ID)
            session.add(conn)
        conn.base_url = None
        conn.token_ciphertext = None
        conn.last_success_at = None
        conn.last_error = None
        conn.last_error_at = None
        await ha_inventory_merge.clear_ha_provenance(session)
        await session.commit()
    logger.info(
        "ha_settings.delete.ok",
        extra={"event": "ha_settings.delete.ok"},
    )
    return Response(status_code=204)
