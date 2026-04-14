"""VPN status endpoint — feature 015 US-2 prominent surfacing.

Summarizes the latest probe + active alerts into one of six states for
the dashboard card and top-nav pill (FR-013):

    OK              — tunnel up, observed IP not in denylist
    LEAK_DETECTED   — active vpn_leak alert exists
    PROBE_UNREACHABLE — probe couldn't reach Deluge (FR-014 soft warning)
    WATCHDOG_DOWN   — no probe heartbeat for >2 rule-engine intervals
    AUTO_STOPPED    — vpn_leak:remediation alert active (3-strike fired)
    UNKNOWN         — no probe has ever run yet

State precedence (first match wins): AUTO_STOPPED > LEAK_DETECTED >
WATCHDOG_DOWN > PROBE_UNREACHABLE > OK > UNKNOWN.

Read-only. No mutation. Polls existing data sources — does NOT trigger a
new probe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.alert import Alert
from app.services.rules.vpn_leak import get_latest_probe

router = APIRouter(tags=["vpn"])

VpnState = Literal[
    "OK",
    "LEAK_DETECTED",
    "PROBE_UNREACHABLE",
    "WATCHDOG_DOWN",
    "AUTO_STOPPED",
    "UNKNOWN",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Strip trailing 'Z' for fromisoformat compat across Python versions.
        return datetime.fromisoformat(s.rstrip("Z"))
    except ValueError:
        return None


def _format_message(
    state: VpnState,
    *,
    observed_ip: str | None,
    age_seconds: int | None,
    probe_error: str | None,
) -> str:
    if state == "OK":
        age_label = _humanize_age(age_seconds) if age_seconds is not None else "moments"
        return f"Tunnel up · exit {observed_ip} · probed {age_label} ago"
    if state == "LEAK_DETECTED":
        ip = observed_ip or "unknown"
        return f"Deluge egressing on {ip} (matches denylist)"
    if state == "PROBE_UNREACHABLE":
        err = probe_error or "no detail"
        return f"Cannot probe Deluge — {err[:120]}"
    if state == "WATCHDOG_DOWN":
        age_label = _humanize_age(age_seconds) if age_seconds else "unknown"
        return f"No probe heartbeat for {age_label} — watchdog may not be running"
    if state == "AUTO_STOPPED":
        ip = observed_ip or "unknown"
        return f"Deluge auto-stopped after consecutive leak detections (latest IP: {ip})"
    return "Awaiting first probe"


def _humanize_age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


@router.get("/vpn-status")
async def get_vpn_status() -> dict[str, Any]:
    probe = get_latest_probe()

    observed_ip = probe.get("observed_ip")
    probe_error = probe.get("error")
    probe_status = probe.get("status")  # "ok" | "leak" | "probe_unreachable" | "unknown"
    checked_at_iso = probe.get("checked_at")
    checked_at_dt = _parse_iso(checked_at_iso)

    now = _utcnow()
    age_seconds: int | None = None
    if checked_at_dt is not None:
        age_seconds = max(0, int((now - checked_at_dt).total_seconds()))

    # Find any active vpn_leak / vpn_leak:remediation alerts
    async with async_session() as session:
        leak_q = (
            select(Alert.id)
            .where(
                Alert.rule_id == "vpn_leak",
                Alert.state.in_(("active", "acknowledged")),
                Alert.suppressed.is_(False),
            )
            .order_by(Alert.created_at.desc())
            .limit(1)
        )
        active_alert_id = (await session.execute(leak_q)).scalar_one_or_none()

        rem_q = (
            select(Alert.id)
            .where(
                Alert.rule_id == "vpn_leak:remediation",
                Alert.state.in_(("active", "acknowledged")),
                Alert.suppressed.is_(False),
            )
            .order_by(Alert.created_at.desc())
            .limit(1)
        )
        active_remediation_alert_id = (
            await session.execute(rem_q)
        ).scalar_one_or_none()

    # State precedence: AUTO_STOPPED > LEAK_DETECTED > WATCHDOG_DOWN >
    # PROBE_UNREACHABLE > OK > UNKNOWN
    watchdog_down_threshold_seconds = 2 * settings.rule_engine_interval_seconds

    state: VpnState
    if active_remediation_alert_id is not None:
        state = "AUTO_STOPPED"
    elif active_alert_id is not None:
        state = "LEAK_DETECTED"
    elif checked_at_dt is None:
        state = "UNKNOWN"
    elif age_seconds is not None and age_seconds > watchdog_down_threshold_seconds:
        state = "WATCHDOG_DOWN"
    elif probe_status == "probe_unreachable":
        state = "PROBE_UNREACHABLE"
    elif probe_status == "leak":
        # Probe saw a denylisted IP. The rule-engine cycle that turns this
        # into an Alert may not have run yet; still surface as a leak so the
        # UI doesn't dishonestly show OK / UNKNOWN during the gap.
        state = "LEAK_DETECTED"
    elif probe_status == "ok":
        state = "OK"
    else:
        state = "UNKNOWN"

    message = _format_message(
        state,
        observed_ip=observed_ip,
        age_seconds=age_seconds,
        probe_error=probe_error,
    )

    return {
        "state": state,
        "observed_ip": observed_ip,
        "last_probe_at": checked_at_iso,
        "last_probe_age_seconds": age_seconds,
        "active_alert_id": active_alert_id,
        "active_remediation_alert_id": active_remediation_alert_id,
        "message": message,
    }
