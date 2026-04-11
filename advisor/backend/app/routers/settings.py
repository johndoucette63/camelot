"""Settings endpoints — thresholds, mutes, notification sinks."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy import select

from app.database import async_session
from app.models.alert_threshold import AlertThreshold
from app.models.notification_sink import NotificationSink
from app.models.rule_mute import RuleMute
from app.services import notification_sender
from app.services.rules import RULES

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
    type: Literal["home_assistant"] = "home_assistant"
    name: str
    enabled: bool = False
    endpoint: AnyHttpUrl
    min_severity: Literal["info", "warning", "critical"] = "critical"


class SinkUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    endpoint: AnyHttpUrl | None = None
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


@router.post("/notifications", status_code=201)
async def create_sink(body: SinkCreate) -> dict[str, Any]:
    sink = NotificationSink(
        type=body.type,
        name=body.name,
        enabled=body.enabled,
        endpoint=str(body.endpoint),
        min_severity=body.min_severity,
    )
    async with async_session() as session:
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
            sink.endpoint = str(body.endpoint)
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

    from fastapi.responses import JSONResponse

    status = 200 if result.get("ok") else 502
    return JSONResponse(status_code=status, content=result)
