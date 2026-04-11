"""Recommendations panel endpoint.

Returns the currently-open alerts plus an optional AI narrative for the
dashboard. The ``ai_narrative`` field stays ``null`` until US4 wires in
``app.services.ai_narrative.get_narrative``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import case, select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.alert import Alert
from app.services.rules import RULES

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

_RULE_NAME_BY_ID = {rule.id: rule.name for rule in RULES}

_SEVERITY_ORDER = case(
    (Alert.severity == "critical", 0),
    (Alert.severity == "warning", 1),
    (Alert.severity == "info", 2),
    else_=3,
)


def _base_rule_id(rule_id: str) -> str:
    return rule_id.split(":", 1)[0]


def _rule_name(rule_id: str) -> str:
    return _RULE_NAME_BY_ID.get(_base_rule_id(rule_id), rule_id)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() + ("Z" if dt.tzinfo is None else "")


async def _target_label(session, alert: Alert) -> str | None:
    if alert.target_type == "device" and alert.target_id is not None:
        from app.models.device import Device

        device = await session.get(Device, alert.target_id)
        if device:
            return device.hostname or device.ip_address
    if alert.target_type == "service" and alert.target_id is not None:
        from app.models.service_definition import ServiceDefinition

        svc = await session.get(ServiceDefinition, alert.target_id)
        if svc:
            return f"{svc.name} ({svc.host_label})"
    return None


def _serialize_alert(alert: Alert, target_label: str | None) -> dict[str, Any]:
    return {
        "id": alert.id,
        "rule_id": alert.rule_id,
        "rule_name": _rule_name(alert.rule_id),
        "severity": alert.severity,
        "target_type": alert.target_type,
        "target_id": alert.target_id,
        "target_label": target_label,
        "message": alert.message,
        "state": alert.state,
        "source": alert.source,
        "suppressed": alert.suppressed,
        "created_at": _iso(alert.created_at),
        "acknowledged_at": _iso(alert.acknowledged_at),
    }


@router.get("")
async def get_recommendations() -> dict[str, Any]:
    async with async_session() as session:
        q = (
            select(Alert)
            .where(
                Alert.state.in_(("active", "acknowledged")),
                Alert.suppressed.is_(False),
            )
            .order_by(_SEVERITY_ORDER, Alert.created_at.desc())
            .options(selectinload(Alert.device), selectinload(Alert.service))
        )
        alerts = (await session.execute(q)).scalars().all()

        active: list[dict[str, Any]] = []
        counts = {"critical": 0, "warning": 0, "info": 0}
        for alert in alerts:
            label = await _target_label(session, alert)
            active.append(_serialize_alert(alert, label))
            if alert.severity in counts:
                counts[alert.severity] += 1

    try:
        from app.services.ai_narrative import get_narrative

        narrative = await get_narrative(alerts)
    except Exception:  # noqa: BLE001
        narrative = None

    return {"active": active, "counts": counts, "ai_narrative": narrative}
