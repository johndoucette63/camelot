"""Alert history log endpoints (list / acknowledge / resolve)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.alert import Alert
from app.services.rules import RULES

router = APIRouter(prefix="/alerts", tags=["alerts"])

RETENTION_DAYS = 30
MAX_LIMIT = 500

_RULE_NAME_BY_ID = {rule.id: rule.name for rule in RULES}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _base_rule_id(rule_id: str) -> str:
    return rule_id.split(":", 1)[0]


def _rule_name(rule_id: str) -> str:
    return _RULE_NAME_BY_ID.get(_base_rule_id(rule_id), rule_id)


async def _target_label(session, alert: Alert) -> str | None:
    if alert.target_type == "device" and alert.target_id is not None:
        from app.models.device import Device

        row = await session.get(Device, alert.target_id)
        return (row.hostname or row.ip_address) if row else None
    if alert.target_type == "service" and alert.target_id is not None:
        from app.models.service_definition import ServiceDefinition

        row = await session.get(ServiceDefinition, alert.target_id)
        return f"{row.name} ({row.host_label})" if row else None
    return None


def _serialize(alert: Alert, label: str | None) -> dict[str, Any]:
    return {
        "id": alert.id,
        "rule_id": alert.rule_id,
        "rule_name": _rule_name(alert.rule_id),
        "severity": alert.severity,
        "target_type": alert.target_type,
        "target_id": alert.target_id,
        "target_label": label,
        "message": alert.message,
        "state": alert.state,
        "source": alert.source,
        "suppressed": alert.suppressed,
        "created_at": _iso(alert.created_at),
        "acknowledged_at": _iso(alert.acknowledged_at),
        "resolved_at": _iso(alert.resolved_at),
        "resolution_source": alert.resolution_source,
    }


@router.get("")
async def list_alerts(
    severity: list[str] | None = Query(None),
    state: list[str] | None = Query(None),
    rule_id: str | None = Query(None),
    device_id: int | None = Query(None),
    service_id: int | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    include_suppressed: bool = Query(False),
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    now = _utcnow()
    clamp_floor = now - timedelta(days=RETENTION_DAYS)

    def _strip_tz(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

    since_val = max(_strip_tz(since) or clamp_floor, clamp_floor)
    until_val = _strip_tz(until) or now

    conds = [Alert.created_at >= since_val, Alert.created_at <= until_val]

    if severity:
        for s in severity:
            if s not in ("info", "warning", "critical"):
                raise HTTPException(status_code=400, detail=f"invalid severity '{s}'")
        conds.append(Alert.severity.in_(severity))
    if state:
        for s in state:
            if s not in ("active", "acknowledged", "resolved"):
                raise HTTPException(status_code=400, detail=f"invalid state '{s}'")
        conds.append(Alert.state.in_(state))
    if rule_id:
        conds.append(
            or_(Alert.rule_id == rule_id, Alert.rule_id.like(f"{rule_id}:%"))
        )
    if device_id is not None:
        conds.append(Alert.device_id == device_id)
    if service_id is not None:
        conds.append(Alert.service_id == service_id)
    if not include_suppressed:
        conds.append(Alert.suppressed.is_(False))

    async with async_session() as session:
        count_q = select(func.count()).select_from(Alert).where(*conds)
        total = (await session.execute(count_q)).scalar_one()

        list_q = (
            select(Alert)
            .where(*conds)
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Alert.device), selectinload(Alert.service))
        )
        rows = (await session.execute(list_q)).scalars().all()

        items = []
        for alert in rows:
            label = await _target_label(session, alert)
            items.append(_serialize(alert, label))

    return {"total": total, "items": items, "limit": limit, "offset": offset}


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int) -> dict[str, Any]:
    async with async_session() as session:
        alert = await session.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="alert not found")
        if alert.state == "resolved":
            raise HTTPException(
                status_code=409, detail="cannot acknowledge a resolved alert"
            )
        if alert.state == "active":
            alert.state = "acknowledged"
            alert.acknowledged_at = _utcnow()
            await session.commit()
            await session.refresh(alert)
        return {
            "id": alert.id,
            "state": alert.state,
            "acknowledged_at": _iso(alert.acknowledged_at),
        }


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int) -> dict[str, Any]:
    async with async_session() as session:
        alert = await session.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="alert not found")
        if alert.state == "resolved":
            raise HTTPException(status_code=409, detail="alert already resolved")
        alert.state = "resolved"
        alert.resolved_at = _utcnow()
        alert.resolution_source = "manual"
        await session.commit()
        await session.refresh(alert)
        return {
            "id": alert.id,
            "state": alert.state,
            "resolved_at": _iso(alert.resolved_at),
            "resolution_source": alert.resolution_source,
        }
