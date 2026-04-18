"""Rule engine background task.

Runs a periodic async loop that:

1. Builds a fresh RuleContext from devices, services, thresholds, Ollama probe.
2. Iterates every rule in ``RULES`` and collects RuleResult objects.
3. Applies the in-memory sustained-window streak filter.
4. Applies the DB-backed 10-minute cool-down filter.
5. Applies the per-(rule, target) mute check (inserts suppressed rows instead
   of skipping so the audit log is complete).
6. Inserts new active alerts via ``ON CONFLICT DO NOTHING`` against the
   partial unique index.
7. Auto-resolves currently-open alerts whose underlying condition has cleared.
8. Delivers non-suppressed active alerts to notification sinks.
9. Prunes alert rows older than 30 days.

All of this is wrapped in ``try/except`` so a single bad cycle never crashes
the background task.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import and_, delete, func, or_, select

from app.config import settings
from app.database import async_session
from app.models.alert import Alert
from app.models.alert_threshold import AlertThreshold
from app.models.device import Device
from app.models.health_check_result import HealthCheckResult
from app.models.notification_sink import NotificationSink
from app.models.rule_mute import RuleMute
from app.models.scan import Scan
from app.models.service_definition import ServiceDefinition
from app.services.rules import RULES
from app.services.rules.base import Rule, RuleContext, RuleResult

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

COOLDOWN_MINUTES = 10
RETENTION_DAYS = 30
RECENT_SCAN_LIMIT = 6
OLLAMA_PROBE_TIMEOUT_SECONDS = 1


@dataclass
class _Streak:
    """Tracks the first-seen timestamp of a rule+target breach.

    The engine holds these in memory per-process. Process restarts reset
    streaks, which is acceptable for a single-admin home lab — the worst
    case is a one-cycle delay re-arming sustained rules after a restart.
    """

    first_seen: datetime
    last_seen: datetime


_STREAKS: dict[tuple[str, str, int | None], _Streak] = {}

# Escalation tracker for rules that opt in via Rule.escalation_threshold.
# Keys are the same shape as _STREAKS (rule_id, target_type, target_id).
# _ESCALATION_COUNTS: how many consecutive cycles have produced a result
# for this key. _ESCALATION_FIRED: keys that have already invoked
# on_escalate in the current breach episode (reset on auto-resolve).
# In-memory only — see 015 spec data-model.md E5 "Escalation counter
# persistence — explicit tradeoff".
_ESCALATION_COUNTS: dict[tuple[str, str, int | None], int] = {}
_ESCALATION_FIRED: set[tuple[str, str, int | None]] = set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _result_rule_id(rule: Rule, result: RuleResult) -> str:
    return result.rule_id_override or rule.id


def _streak_key(rule_id: str, result: RuleResult) -> tuple[str, str, int | None]:
    return (rule_id, result.target_type, result.target_id)


async def _load_thresholds(session) -> dict[str, Decimal]:
    rows = (await session.execute(select(AlertThreshold))).scalars().all()
    return {r.key: r.value for r in rows}


async def _load_latest_health_results(session) -> dict[int, HealthCheckResult]:
    """Return the most recent HealthCheckResult for each service_id."""
    result = await session.execute(
        select(HealthCheckResult).order_by(HealthCheckResult.checked_at.desc())
    )
    latest: dict[int, HealthCheckResult] = {}
    for row in result.scalars():
        if row.service_id not in latest:
            latest[row.service_id] = row
    return latest


async def _probe_ollama() -> bool:
    """Cheap Ollama healthcheck — 1-second GET /api/tags."""
    url = f"{settings.ollama_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
        return resp.status_code == 200
    except (httpx.RequestError, httpx.TimeoutException):
        return False


async def _probe_frigate_stats() -> dict | None:
    """Fetch Frigate's /api/stats for feature-017 rules.

    Returns the parsed JSON payload on success, or ``None`` if Frigate is
    unreachable or responds with an error. Rules treat ``None`` as "no
    data this cycle — skip" so a Frigate outage does not cascade into
    spurious alerts from the two Frigate rules.
    """
    url = f"{settings.frigate_url.rstrip('/')}/api/stats"
    try:
        async with httpx.AsyncClient(
            timeout=settings.frigate_probe_timeout_seconds
        ) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        payload = resp.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.RequestError, httpx.TimeoutException, ValueError):
        return None


async def build_context(session, app) -> RuleContext:
    now = _utcnow()

    devices_result = await session.execute(select(Device))
    devices = devices_result.scalars().all()

    services_result = await session.execute(
        select(ServiceDefinition).where(ServiceDefinition.enabled.is_(True))
    )
    services = services_result.scalars().all()

    health_results = await _load_latest_health_results(session)
    thresholds = await _load_thresholds(session)

    scans_result = await session.execute(
        select(Scan).order_by(Scan.started_at.desc()).limit(RECENT_SCAN_LIMIT)
    )
    recent_scans = list(scans_result.scalars())

    ollama_healthy = await _probe_ollama()
    frigate_stats = await _probe_frigate_stats()
    container_state = getattr(app.state, "container_state", {}) if app else {}

    return RuleContext(
        now=now,
        session=session,
        devices=list(devices),
        services=list(services),
        health_results=health_results,
        container_state=container_state,
        thresholds=thresholds,
        ollama_healthy=ollama_healthy,
        recent_scans=recent_scans,
        device_metrics={},
        frigate_stats=frigate_stats,
    )


def _apply_sustained_window(
    rule: Rule,
    results: list[RuleResult],
    now: datetime,
) -> list[RuleResult]:
    """Apply the in-memory streak map.

    A result whose streak has survived at least ``rule.sustained_window`` is
    allowed through; shorter streaks are dropped. Rules with a zero window
    always pass immediately.
    """
    out: list[RuleResult] = []
    seen_keys: set[tuple[str, str, int | None]] = set()

    for result in results:
        rid = _result_rule_id(rule, result)
        key = _streak_key(rid, result)
        seen_keys.add(key)

        streak = _STREAKS.get(key)
        if streak is None:
            _STREAKS[key] = _Streak(first_seen=now, last_seen=now)
            if rule.sustained_window == timedelta(0):
                out.append(result)
            continue

        streak.last_seen = now
        if now - streak.first_seen >= rule.sustained_window:
            out.append(result)

    # Drop streaks for targets that cleared this cycle (for this rule).
    for key in list(_STREAKS.keys()):
        if key[0] == rule.id or key[0].startswith(rule.id + ":"):
            if key not in seen_keys:
                del _STREAKS[key]

    return out


async def _filter_cooldown(
    session, rule: Rule, results: list[RuleResult], now: datetime
) -> list[RuleResult]:
    if not results:
        return results

    cutoff = now - timedelta(minutes=COOLDOWN_MINUTES)
    out: list[RuleResult] = []
    for result in results:
        rid = _result_rule_id(rule, result)
        q = select(Alert.id).where(
            Alert.rule_id == rid,
            Alert.target_type == result.target_type,
            Alert.state == "resolved",
            Alert.resolved_at > cutoff,
        )
        if result.target_id is None:
            q = q.where(Alert.target_id.is_(None))
        else:
            q = q.where(Alert.target_id == result.target_id)
        q = q.limit(1)
        existing = (await session.execute(q)).scalar_one_or_none()
        if existing is None:
            out.append(result)
    return out


async def _is_muted(
    session, rule: Rule, result: RuleResult, now: datetime
) -> bool:
    """Check whether an active mute exists for this (rule, target)."""
    rid = _result_rule_id(rule, result)
    q = select(RuleMute.id).where(
        RuleMute.rule_id == rid,
        RuleMute.target_type == result.target_type,
        RuleMute.cancelled_at.is_(None),
        RuleMute.expires_at > now,
    )
    if result.target_id is None:
        q = q.where(RuleMute.target_id.is_(None))
    else:
        q = q.where(RuleMute.target_id == result.target_id)
    q = q.limit(1)
    return (await session.execute(q)).scalar_one_or_none() is not None


def _device_id_for(result: RuleResult) -> int | None:
    return result.target_id if result.target_type == "device" else None


def _service_id_for(result: RuleResult) -> int | None:
    return result.target_id if result.target_type == "service" else None


async def _insert_alert(
    session, rule: Rule, result: RuleResult, *, suppressed: bool, now: datetime
) -> int | None:
    """Insert a new alert row or re-activate the most recent resolved alert
    for the same (rule_id, target_type, target_id).

    Re-activation prevents duplicate rows for flapping devices — each
    (rule, target) combo gets at most one row that toggles between active
    and resolved.

    In production a partial unique index enforces uniqueness for active
    rows; the application-level check covers SQLite in tests.
    """
    rid = _result_rule_id(rule, result)

    # Check for an existing open (non-resolved, non-suppressed) row.
    existing_q = select(Alert.id).where(
        Alert.rule_id == rid,
        Alert.target_type == result.target_type,
        Alert.state != "resolved",
        Alert.suppressed.is_(False),
    )
    if result.target_id is None:
        existing_q = existing_q.where(Alert.target_id.is_(None))
    else:
        existing_q = existing_q.where(Alert.target_id == result.target_id)
    existing = (await session.execute(existing_q.limit(1))).scalar_one_or_none()
    if existing is not None:
        return None

    # Try to re-activate the most recent resolved alert for this target
    # instead of creating a new row. This eliminates duplicate IPs in the
    # alert list caused by devices that flap between online and offline.
    reactivate_q = (
        select(Alert)
        .where(
            Alert.rule_id == rid,
            Alert.target_type == result.target_type,
            Alert.state == "resolved",
        )
        .order_by(Alert.resolved_at.desc())
    )
    if result.target_id is None:
        reactivate_q = reactivate_q.where(Alert.target_id.is_(None))
    else:
        reactivate_q = reactivate_q.where(Alert.target_id == result.target_id)
    resolved_alert = (
        await session.execute(reactivate_q.limit(1))
    ).scalar_one_or_none()

    if resolved_alert is not None:
        resolved_alert.state = "active"
        resolved_alert.message = result.message
        resolved_alert.created_at = now
        resolved_alert.acknowledged_at = None
        resolved_alert.resolved_at = None
        resolved_alert.resolution_source = None
        resolved_alert.suppressed = suppressed
        await session.flush()
        return resolved_alert.id

    alert = Alert(
        device_id=_device_id_for(result),
        service_id=_service_id_for(result),
        severity=rule.severity,
        message=result.message,
        created_at=now,
        rule_id=rid,
        target_type=result.target_type,
        target_id=result.target_id,
        state="active",
        source="rule",
        suppressed=suppressed,
    )
    session.add(alert)
    await session.flush()
    return alert.id


async def _auto_resolve(
    session,
    rule: Rule,
    currently_breaching: set[tuple[str, str, int | None]],
    now: datetime,
) -> int:
    """Resolve any open alerts for this rule whose target is no longer breaching."""
    rid_prefix_match = rule.id  # unknown_device overrides this per-result via rule_id_override
    q = select(Alert).where(
        or_(
            Alert.rule_id == rid_prefix_match,
            Alert.rule_id.like(f"{rid_prefix_match}:%"),
        ),
        Alert.state.in_(("active", "acknowledged")),
        Alert.suppressed.is_(False),
    )
    open_alerts = (await session.execute(q)).scalars().all()

    resolved = 0
    for alert in open_alerts:
        key = (alert.rule_id, alert.target_type, alert.target_id)
        if key in currently_breaching:
            continue
        alert.state = "resolved"
        alert.resolved_at = now
        alert.resolution_source = "auto"
        resolved += 1
        # Reset escalation state for the cleared key so the next breach
        # episode starts fresh.
        _ESCALATION_COUNTS.pop(key, None)
        _ESCALATION_FIRED.discard(key)
    return resolved


async def _maybe_escalate(
    rule: Rule, result: RuleResult, ctx: RuleContext
) -> RuleResult | None:
    """Track per-target consecutive-fire counts; invoke on_escalate once
    when the threshold is hit.

    Returns a follow-up RuleResult (typically with rule_id_override set to
    "<rule_id>:remediation") or None. The caller is responsible for
    feeding the returned result back through the normal alert pipeline.
    """
    if rule.escalation_threshold is None:
        return None

    rid = _result_rule_id(rule, result)
    key = _streak_key(rid, result)
    _ESCALATION_COUNTS[key] = _ESCALATION_COUNTS.get(key, 0) + 1

    if (
        _ESCALATION_COUNTS[key] >= rule.escalation_threshold
        and key not in _ESCALATION_FIRED
    ):
        _ESCALATION_FIRED.add(key)
        try:
            return await rule.on_escalate(result, ctx)
        except Exception:  # noqa: BLE001 — escalation must not crash the cycle
            logger.exception(
                "rule_engine.escalation.error",
                extra={"event": "rule_engine.escalation.error", "rule_id": rid},
            )
    return None


async def _prune_old_alerts(session, now: datetime) -> int:
    cutoff = now - timedelta(days=RETENTION_DAYS)
    res = await session.execute(
        delete(Alert).where(
            and_(Alert.state == "resolved", Alert.resolved_at < cutoff)
        )
    )
    return res.rowcount or 0


async def _deliver_notifications(session, alert_ids: list[int]) -> tuple[int, int]:
    """Deliver newly-created alerts to notification sinks.

    Returns ``(sent, failed)`` counts across all sinks and alerts. No
    exception ever escapes — sink errors are swallowed in
    ``notification_sender.deliver``. Consistent with FR-026.

    Short-circuits when no enabled sinks exist (FR-025 hot-reload: a
    sink disabled mid-cycle must not receive anything on the next
    cycle). We re-query the enabled-sinks list every cycle so a toggle
    is visible without a process restart.
    """
    from app.services import notification_sender

    if not alert_ids:
        return (0, 0)

    enabled_count = (
        await session.execute(
            select(func.count())
            .select_from(NotificationSink)
            .where(NotificationSink.enabled.is_(True))
        )
    ).scalar_one()
    if enabled_count == 0:
        return (0, 0)

    sent = 0
    failed = 0
    alerts = (
        (await session.execute(select(Alert).where(Alert.id.in_(alert_ids))))
        .scalars()
        .all()
    )
    for alert in alerts:
        if alert.suppressed:
            continue
        try:
            attempted, succeeded = await notification_sender.deliver(session, alert)
        except Exception as exc:  # noqa: BLE001 — belt-and-suspenders
            logger.warning(
                "rule_engine.ha.delivery_failed",
                extra={"event": "rule_engine.ha.delivery_failed", "error": str(exc)},
            )
            continue
        sent += succeeded
        failed += attempted - succeeded
    return (sent, failed)


async def run_cycle(app) -> dict:
    cycle_start = time.monotonic()
    stats = {
        "rules_evaluated": 0,
        "alerts_created": 0,
        "alerts_resolved": 0,
        "alerts_suppressed": 0,
        "alerts_pruned": 0,
        "ha_notifications_sent": 0,
        "ha_notifications_failed": 0,
    }

    async with async_session() as session:
        ctx = await build_context(session, app)

        new_alert_ids: list[int] = []

        for rule in RULES:
            stats["rules_evaluated"] += 1
            try:
                raw_results = await rule.evaluate(ctx)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "rule_engine.rule.error",
                    extra={"event": "rule_engine.rule.error", "rule_id": rule.id},
                )
                continue

            sustained = _apply_sustained_window(rule, raw_results, ctx.now)
            after_cooldown = await _filter_cooldown(session, rule, sustained, ctx.now)

            currently_breaching: set[tuple[str, str, int | None]] = set()
            escalation_followups: list[RuleResult] = []
            for result in after_cooldown:
                rid = _result_rule_id(rule, result)
                currently_breaching.add(
                    (rid, result.target_type, result.target_id)
                )

                muted = await _is_muted(session, rule, result, ctx.now)
                inserted_id = await _insert_alert(
                    session, rule, result, suppressed=muted, now=ctx.now
                )
                if inserted_id is not None:
                    if muted:
                        stats["alerts_suppressed"] += 1
                    else:
                        new_alert_ids.append(inserted_id)
                        stats["alerts_created"] += 1

                # Check for escalation only after the alert has been recorded
                # (don't escalate suppressed/muted breaches).
                if not muted:
                    followup = await _maybe_escalate(rule, result, ctx)
                    if followup is not None:
                        escalation_followups.append(followup)

            # Emit escalation follow-up RuleResults (typically remediation
            # alerts) through the same alert pipeline. Track them for
            # currently_breaching so auto-resolve doesn't immediately clear
            # them on the next cycle.
            for followup in escalation_followups:
                rid = _result_rule_id(rule, followup)
                currently_breaching.add(
                    (rid, followup.target_type, followup.target_id)
                )
                muted = await _is_muted(session, rule, followup, ctx.now)
                inserted_id = await _insert_alert(
                    session, rule, followup, suppressed=muted, now=ctx.now
                )
                if inserted_id is not None:
                    if muted:
                        stats["alerts_suppressed"] += 1
                    else:
                        new_alert_ids.append(inserted_id)
                        stats["alerts_created"] += 1

            stats["alerts_resolved"] += await _auto_resolve(
                session, rule, currently_breaching, ctx.now
            )

        stats["alerts_pruned"] += await _prune_old_alerts(session, ctx.now)

        sent, failed = await _deliver_notifications(session, new_alert_ids)
        stats["ha_notifications_sent"] += sent
        stats["ha_notifications_failed"] += failed

        await session.commit()

    stats["duration_ms"] = int((time.monotonic() - cycle_start) * 1000)
    return stats


async def run(app) -> None:
    """Long-running background task. Call once from lifespan."""
    await asyncio.sleep(2)

    while True:
        try:
            stats = await run_cycle(app)
            logger.info(
                "rule_engine.cycle.completed",
                extra={"event": "rule_engine.cycle.completed", **stats},
            )
        except asyncio.CancelledError:
            logger.info("Rule engine shutting down")
            raise
        except Exception:
            logger.exception("rule_engine.cycle.failed")

        await asyncio.sleep(settings.rule_engine_interval_seconds)
