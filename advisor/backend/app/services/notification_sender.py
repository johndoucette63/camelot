"""Outbound notification delivery (Home Assistant webhooks).

Called by the rule engine after a new non-suppressed alert is inserted.
All failures are swallowed and logged so the engine loop is never
impacted (FR-026). Delivery is fire-and-forget with a 5-second timeout.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.alert import Alert
from app.models.notification_sink import NotificationSink

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def _meets_cutoff(sink_min: str, alert_severity: str) -> bool:
    return _SEVERITY_ORDER.get(alert_severity, 0) >= _SEVERITY_ORDER.get(
        sink_min, 2
    )


def _payload(alert: Alert) -> dict[str, Any]:
    return {
        "message": alert.message,
        "target": {
            "type": alert.target_type,
            "id": alert.target_id,
        },
        "severity": alert.severity,
        "rule_id": alert.rule_id,
        "created_at": _iso(alert.created_at),
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


async def deliver(session, alert: Alert) -> tuple[int, int]:
    """Deliver an alert to every enabled sink whose cutoff matches.

    Returns ``(attempted, succeeded)`` so the engine can maintain
    accurate HA counters in its cycle stats. No exception ever escapes
    this function — the rule engine loop is impermeable to sink errors
    (FR-026).
    """
    q = select(NotificationSink).where(NotificationSink.enabled.is_(True))
    sinks = (await session.execute(q)).scalars().all()

    attempted = 0
    succeeded = 0
    for sink in sinks:
        if not _meets_cutoff(sink.min_severity, alert.severity):
            continue
        attempted += 1
        ok = await _deliver_one(sink, alert)
        if ok:
            succeeded += 1
    return (attempted, succeeded)


async def _deliver_one(sink: NotificationSink, alert: Alert) -> bool:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=float(settings.ha_webhook_timeout_seconds)
        ) as client:
            resp = await client.post(sink.endpoint, json=_payload(alert))
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code >= 400:
            logger.warning(
                "rule_engine.ha.delivery_failed",
                extra={
                    "event": "rule_engine.ha.delivery_failed",
                    "sink_id": sink.id,
                    "alert_id": alert.id,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                },
            )
            return False
        logger.info(
            "rule_engine.ha.delivered",
            extra={
                "event": "rule_engine.ha.delivered",
                "sink_id": sink.id,
                "alert_id": alert.id,
                "latency_ms": latency_ms,
            },
        )
        return True
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.warning(
            "rule_engine.ha.delivery_failed",
            extra={
                "event": "rule_engine.ha.delivery_failed",
                "sink_id": sink.id,
                "alert_id": alert.id,
                "error": str(exc),
            },
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "rule_engine.ha.delivery_failed",
            extra={
                "event": "rule_engine.ha.delivery_failed",
                "sink_id": sink.id,
                "alert_id": alert.id,
                "error": str(exc),
            },
        )
        return False


async def send_test(sink: NotificationSink) -> dict[str, Any]:
    """Fire a synthetic test payload through a sink for the settings UI."""
    t0 = time.monotonic()
    payload = {
        "message": "Camelot advisor test notification",
        "target": {"type": "system", "id": None},
        "severity": "info",
        "rule_id": "test",
        "created_at": None,
    }
    try:
        async with httpx.AsyncClient(
            timeout=float(settings.ha_webhook_timeout_seconds)
        ) as client:
            resp = await client.post(sink.endpoint, json=payload)
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code >= 400:
            return {
                "ok": False,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}",
            }
        return {"ok": True, "status_code": resp.status_code, "latency_ms": latency_ms}
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        return {"ok": False, "error": str(exc)}
