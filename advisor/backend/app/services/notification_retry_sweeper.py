"""Notification delivery retry sweeper (feature 016, US-3).

One pass through every alert row whose HA-native delivery failed and
whose ``delivery_next_attempt_at`` has matured. For each row:

1. Re-dispatch through ``notification_sender._deliver_one_ha`` to the
   matching enabled ``type="home_assistant"`` sink(s). The delivery
   helper advances the state machine on the alert row:
   ``failed → failed`` with the next backoff delay, or ``failed → sent``
   on success.
2. When ``delivery_attempt_count`` reaches the terminal threshold
   (``notification_sender.TERMINAL_AFTER_ATTEMPTS`` = 4 failed
   attempts) the sweeper flips ``delivery_status`` to ``terminal`` and
   inserts a ``notification_delivery_failure`` recommendation alert
   describing the give-up — FR-020.

Backoff interpretation
----------------------

Research R6 specifies the exponential backoff table as 30 s / 60 s /
120 s / 240 s. R6 also describes the total budget as "~5 min wall
clock". The raw arithmetic (30+60+120+240) totals 450 s ≈ 7.5 min;
this module follows the R6 table verbatim because it matches the
``_RETRY_BACKOFF_SECONDS`` constants in ``notification_sender`` exactly
and because the 5-min label in R6 is documented as approximate. The
quickstart Step 5 validation is written against this table, not the
5-min label.

One-sink vs multi-sink
----------------------

The ``delivery_*`` columns live on the ALERT row, not on a
``(sink, alert)`` join row. For the v1 home-lab scope we assume a
single HA-native sink (the admin's phone); the sweeper dispatches to
the first enabled matching sink it finds and records the outcome on
the alert. If more than one HA sink exists, each successful dispatch
advances the state machine the same way, so a second sink's success
still flips the alert to ``sent``. On failures across all sinks the
row remains ``failed`` with the incremented attempt count.

All failures at any level are caught — the sweeper makes best-effort
progress on remaining rows and never crashes the poller cycle.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.models.alert import Alert
from app.models.notification_sink import NotificationSink
from app.services import notification_sender
from app.services.notification_sender import (
    TERMINAL_AFTER_ATTEMPTS,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _load_due_alerts(session, now: datetime) -> list[Alert]:
    """Return failed alerts whose next-attempt time has matured.

    Only picks up rows with ``delivery_status='failed'`` and a non-null
    ``delivery_next_attempt_at`` that is already in the past. ``sent``,
    ``terminal``, ``suppressed``, ``n/a``, and ``pending`` rows are
    never swept. Sorted by next-attempt time so aged rows go first.
    """
    q = (
        select(Alert)
        .where(
            Alert.delivery_status == "failed",
            Alert.delivery_next_attempt_at.is_not(None),
            Alert.delivery_next_attempt_at <= now,
        )
        .order_by(Alert.delivery_next_attempt_at)
    )
    return list((await session.execute(q)).scalars().all())


async def _load_ha_sinks(session) -> list[NotificationSink]:
    """Return every enabled HA-native sink, ordered by id (stable)."""
    q = (
        select(NotificationSink)
        .where(
            NotificationSink.enabled.is_(True),
            NotificationSink.type == "home_assistant",
        )
        .order_by(NotificationSink.id)
    )
    return list((await session.execute(q)).scalars().all())


def _build_terminal_recommendation(alert: Alert, now: datetime) -> Alert:
    """Build a recommendation alert row describing a give-up."""
    return Alert(
        severity="warning",
        message=(
            f"Alert #{alert.id} ({alert.rule_id}) not delivered to Home "
            f"Assistant after {TERMINAL_AFTER_ATTEMPTS} attempts"
        ),
        created_at=now,
        rule_id="notification_delivery_failure",
        target_type="system",
        target_id=alert.id,
        state="active",
        source="rule",
        suppressed=False,
        # Do not forward the recommendation itself — that would risk a
        # delivery-failure-about-delivery-failure loop if HA is still
        # down. The recommendation is visible in the advisor UI.
        delivery_status="n/a",
    )


async def _ensure_terminal_recommendation(
    session, alert: Alert, now: datetime
) -> bool:
    """Insert a terminal-failure recommendation if one isn't already present.

    Returns ``True`` if a new row was inserted.
    """
    q = (
        select(Alert.id)
        .where(
            Alert.rule_id == "notification_delivery_failure",
            Alert.target_type == "system",
            Alert.target_id == alert.id,
        )
        .limit(1)
    )
    existing = (await session.execute(q)).scalar_one_or_none()
    if existing is not None:
        return False
    session.add(_build_terminal_recommendation(alert, now))
    return True


async def _promote_to_terminal(session, alert: Alert, now: datetime) -> None:
    """Flip a failed alert to terminal and insert the give-up recommendation."""
    alert.delivery_status = "terminal"
    alert.delivery_next_attempt_at = None
    alert.delivery_last_attempt_at = now
    await _ensure_terminal_recommendation(session, alert, now)
    logger.warning(
        "notification.ha.terminal",
        extra={
            "event": "notification.ha.terminal",
            "alert_id": alert.id,
            "rule_id": alert.rule_id,
            "attempt_count": alert.delivery_attempt_count,
        },
    )


async def _sweep_one(
    session,
    alert: Alert,
    sinks: list[NotificationSink],
    now: datetime,
) -> dict[str, Any]:
    """Process one alert — redispatch, or promote to terminal.

    Never raises; exceptions in the delivery path are already swallowed
    by ``_deliver_one_ha``. Returns a small stats dict for the caller's
    log line.
    """
    # If we're already at (or over) the terminal threshold before any
    # new dispatch, promote immediately — we reached this row because
    # the previous cycle exhausted the backoff table and scheduled no
    # further retry (``delivery_next_attempt_at`` went NULL and then
    # was never updated). In practice this path is rare because the
    # delivery helper clears the schedule at attempt 4; the sweeper
    # filter already excludes NULL-schedule rows.
    if alert.delivery_attempt_count >= TERMINAL_AFTER_ATTEMPTS:
        await _promote_to_terminal(session, alert, now)
        return {"alert_id": alert.id, "outcome": "terminal"}

    if not sinks:
        # No HA sinks configured — give up rather than loop forever.
        await _promote_to_terminal(session, alert, now)
        return {"alert_id": alert.id, "outcome": "terminal_no_sink"}

    # Single-dispatch-per-sweep policy (documented in module docstring):
    # dispatch to the first enabled HA-native sink only so the per-alert
    # attempt counter is incremented at most once per sweep. Multiple
    # HA-native sinks (one physical HA instance, multiple notify
    # services) share the same delivery state; a second sink's retry
    # would double-count attempts and burn the retry budget in half the
    # wall clock.
    sink = sinks[0]
    ok = await notification_sender._deliver_one_ha(session, sink, alert)

    # After the delivery helper advanced the state machine, check if we
    # just crossed the terminal threshold. The helper records a failure
    # but stops scheduling future retries past attempt 4 — this block
    # catches that and promotes the row.
    if (
        not ok
        and alert.delivery_status == "failed"
        and alert.delivery_attempt_count >= TERMINAL_AFTER_ATTEMPTS
    ):
        await _promote_to_terminal(session, alert, now)
        return {"alert_id": alert.id, "outcome": "terminal"}

    return {
        "alert_id": alert.id,
        "outcome": "sent" if ok else "failed",
        "attempt_count": alert.delivery_attempt_count,
    }


async def sweep(session) -> dict[str, Any]:
    """Run one pass of retry deliveries.

    Called from the HA poller cycle after the Thread-table refresh
    (``ha_poller.run_cycle``). Safe to call with no enabled HA sinks —
    in that case any due failed rows are promoted to ``terminal``.

    Never raises. Returns a small stats dict suitable for a structured
    log line at the caller's discretion.
    """
    now = _utcnow()
    stats = {
        "event": "notification.retry_sweep",
        "picked": 0,
        "sent": 0,
        "failed": 0,
        "terminal": 0,
    }

    try:
        due_alerts = await _load_due_alerts(session, now)
        sinks = await _load_ha_sinks(session)
    except Exception:  # noqa: BLE001 — sweeper must not crash the cycle
        logger.exception(
            "notification.retry_sweep.select_failed",
            extra={"event": "notification.retry_sweep.select_failed"},
        )
        return stats

    stats["picked"] = len(due_alerts)

    for alert in due_alerts:
        try:
            outcome = await _sweep_one(session, alert, sinks, now)
        except Exception:  # noqa: BLE001 — one broken row must not stop others
            logger.exception(
                "notification.retry_sweep.alert_failed",
                extra={
                    "event": "notification.retry_sweep.alert_failed",
                    "alert_id": alert.id,
                },
            )
            continue

        if outcome.get("outcome") == "sent":
            stats["sent"] += 1
        elif outcome.get("outcome", "").startswith("terminal"):
            stats["terminal"] += 1
        else:
            stats["failed"] += 1

    # Single commit for the whole pass — keeps the DB consistent with
    # the caller's ``ha_poller.run_cycle`` commit style. The caller may
    # also commit its own state in the same session; that is fine.
    try:
        await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "notification.retry_sweep.commit_failed",
            extra={"event": "notification.retry_sweep.commit_failed"},
        )
        await session.rollback()

    if stats["picked"] > 0:
        logger.info("notification.retry_sweep", extra=stats)
    return stats
