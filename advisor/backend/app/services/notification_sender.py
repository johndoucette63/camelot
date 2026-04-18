"""Outbound notification delivery (webhook + Home Assistant native).

Called by the rule engine after a new non-suppressed alert is inserted,
and by the HA-poller-driven retry sweeper for rows whose
``delivery_next_attempt_at`` has matured.

Two sink variants are supported:

* ``type="webhook"`` — fire-and-forget POST to an arbitrary URL (from
  011-recommendations-alerts). Preserves existing semantics: no retry
  bookkeeping, no state recorded on the alert row, delivery failures
  logged and swallowed.

* ``type="home_assistant"`` — POST to the HA-native
  ``/api/services/notify/<service>`` endpoint resolved through the
  singleton ``home_assistant_connections`` row (feature 016). Records
  delivery outcomes on the alert row (``delivery_status``,
  ``delivery_attempt_count``, ``delivery_last_attempt_at``,
  ``delivery_next_attempt_at``) so the retry sweeper can drive the 5-min
  exponential-backoff state machine per research R6.

All failures are swallowed and logged — no exception ever leaves this
module, matching the fire-and-forget semantics established in 011.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.alert import Alert
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.notification_sink import NotificationSink
from app.models.rule_mute import RuleMute
from app.services import ha_client
from app.services.ha_client import (
    HAAuthError,
    HAClientError,
    HAUnexpectedPayloadError,
    HAUnreachableError,
)

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}

# R6 backoff table — delay after a failed attempt until the next
# scheduled retry. Keyed by the attempt count we JUST incremented to
# (the count AFTER this failure is recorded). Each entry is read as
# "the failure that advanced the count to <key> schedules the next
# attempt <value> seconds later."
#
#   count becomes 1 (attempt 1 failed) → +30 s to attempt 2
#   count becomes 2 (attempt 2 failed) → +30 s to attempt 3    [matches T059]
#   count becomes 3 (attempt 3 failed) → +60 s to attempt 4    [matches T059]
#   count becomes 4 (attempt 4 failed) → +120 s grace to terminal [matches T059]
#
# At count == 4 (``TERMINAL_AFTER_ATTEMPTS``) the sweeper's pre-dispatch
# check promotes the row to ``terminal`` before another call_notify
# happens, so the "grace" entry is a belt-and-suspenders default that
# would only be observed if the pre-check were removed.
#
# Cumulative wall-clock from the initial failure to the terminal
# promotion pass: 30 + 30 + 60 = 120 s ≈ 2 min, plus the sweep cadence
# (default HA poll interval 60 s) for the terminal pass. R6 describes
# the budget as "~5 min total"; the implementation lands well inside
# that envelope. The test ``test_backoff_progression_to_terminal`` in
# ``test_notification_retry_sweeper.py`` asserts the exact delays.
#
# Note: research R6's table written as
# ``attempt 2 = 30s, attempt 3 = 60s, attempt 4 = 120s, terminal = 240s``
# is the total elapsed time for each attempt after the initial
# failure. In the per-transition view used by this module, the first
# transition (attempt 1 → attempt 2) takes 30s, the second (2 → 3)
# takes another 30s (= 60 - 30), and so on. T059 in tasks.md pins the
# per-transition view.
_RETRY_BACKOFF_SECONDS: dict[int, int] = {
    1: 30,
    2: 30,
    3: 60,
    4: 120,
}

# After this many failed attempts, the next sweep marks the alert
# ``terminal`` rather than scheduling another attempt.
TERMINAL_AFTER_ATTEMPTS = 4

_HA_NOTIFY_TIMEOUT_SECONDS = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def _ha_payload(alert: Alert) -> dict[str, Any]:
    """Build the HA-native notify payload per research R7."""
    return {
        "title": f"Camelot: {alert.rule_id}",
        "message": alert.message,
        "data": {
            "severity": alert.severity,
            "rule_id": alert.rule_id,
            "target_type": alert.target_type,
            "target_id": alert.target_id,
            "alert_id": alert.id,
        },
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


async def _is_alert_muted(session, alert: Alert, now: datetime) -> bool:
    """Check whether an active RuleMute covers this alert."""
    q = select(RuleMute.id).where(
        RuleMute.rule_id == alert.rule_id,
        RuleMute.target_type == alert.target_type,
        RuleMute.cancelled_at.is_(None),
        RuleMute.expires_at > now,
    )
    if alert.target_id is None:
        q = q.where(RuleMute.target_id.is_(None))
    else:
        q = q.where(RuleMute.target_id == alert.target_id)
    q = q.limit(1)
    return (await session.execute(q)).scalar_one_or_none() is not None


def _is_ha_native_sink(sink: NotificationSink) -> bool:
    """Return True when this sink should dispatch via HA's notify REST.

    Two sink shapes coexist:

    * ``type="home_assistant"`` with a webhook URL endpoint — the
      F4.5/011 shape (``http://homeassistant.holygrail/api/webhook/...``).
      Treated as a webhook sink; dispatch via ``_deliver_one`` and do
      not record delivery state on the alert row.
    * ``type="home_assistant"`` with a bare notify service suffix +
      ``home_assistant_id`` FK set — the feature-016/US-3 shape. Treated
      as a native HA notify sink; dispatch via ``_deliver_one_ha`` with
      retry state recorded on the alert row.

    The distinguishing signal is the FK; absent that, we fall back to
    endpoint shape (``://`` anywhere in the string ⇒ webhook). This
    keeps existing prod rows working unchanged.
    """
    if sink.home_assistant_id is not None:
        return True
    if "://" in (sink.endpoint or ""):
        return False
    return True


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
        ha_native = _is_ha_native_sink(sink)

        if not _meets_cutoff(sink.min_severity, alert.severity):
            # Below threshold for this sink. For HA-native sinks we
            # set an explicit "n/a" marker on the alert row so the UI
            # can show "not forwarded" without ambiguity (FR-019 /
            # contract §4). Webhook sinks preserve legacy silent-drop
            # semantics. Never clobber a terminal / sent / suppressed
            # marker from a previously-iterated sink.
            if ha_native and alert.delivery_status in ("pending",):
                _mark_status(alert, "n/a")
            continue

        attempted += 1

        if ha_native:
            ok = await _deliver_one_ha(session, sink, alert)
        else:
            ok = await _deliver_one(sink, alert)

        if ok:
            succeeded += 1
    return (attempted, succeeded)


# ── Webhook sink (F4.5) — preserved exactly ────────────────────────────


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


# ── Home Assistant sink (feature 016 / US-3) ───────────────────────────


def _mark_status(alert: Alert, status: str) -> None:
    """Set a terminal-ish delivery status on the alert row.

    Used for "suppressed"/"n/a" markers where no retry is scheduled.
    Keeps ``delivery_next_attempt_at`` NULL so the sweeper never picks
    the row up again.
    """
    alert.delivery_status = status
    alert.delivery_next_attempt_at = None


def _record_success(alert: Alert, now: datetime) -> None:
    alert.delivery_status = "sent"
    alert.delivery_attempt_count = max(alert.delivery_attempt_count or 0, 1)
    alert.delivery_last_attempt_at = now
    alert.delivery_next_attempt_at = None


def _record_failure(alert: Alert, now: datetime) -> None:
    """Record a failed attempt and schedule the next retry.

    The schedule delay is looked up by the incremented attempt count
    (the count AFTER this failure is recorded). See the commentary on
    ``_RETRY_BACKOFF_SECONDS`` for the table and keying rationale.

    When ``delivery_attempt_count`` reaches ``TERMINAL_AFTER_ATTEMPTS``
    the sweeper promotes the row to ``terminal`` on the next sweep
    pass (via its pre-dispatch check); the "grace" delay scheduled
    here gives the 5-minute budget's final window a finite end even
    if the sweep cadence stalls.
    """
    new_count = (alert.delivery_attempt_count or 0) + 1
    alert.delivery_status = "failed"
    alert.delivery_attempt_count = new_count
    alert.delivery_last_attempt_at = now
    delay = _RETRY_BACKOFF_SECONDS.get(new_count)
    if delay is None:
        alert.delivery_next_attempt_at = None
    else:
        alert.delivery_next_attempt_at = now + timedelta(seconds=delay)


async def _load_ha_connection(
    session, sink: NotificationSink
) -> HomeAssistantConnection | None:
    """Load the HA connection this sink targets.

    Returns ``None`` when the sink has no ``home_assistant_id`` or the
    referenced row has no base URL configured. Callers should treat
    this as a delivery failure and record it as such — a mis-configured
    sink should not crash the cycle.
    """
    if sink.home_assistant_id is None:
        # Fall back to the singleton (id=1) — some callers construct
        # sinks without explicit FK wiring, e.g. legacy rows or sinks
        # created before migration 008 landed. Both paths end at the
        # same connection row in v1 (only one HA instance).
        conn = await session.get(HomeAssistantConnection, 1)
    else:
        conn = await session.get(
            HomeAssistantConnection, sink.home_assistant_id
        )
    if conn is None or conn.base_url is None:
        return None
    return conn


async def _deliver_one_ha(
    session, sink: NotificationSink, alert: Alert
) -> bool:
    """Attempt one HA-native notify delivery.

    Writes the outcome to the alert row via ``_record_success`` /
    ``_record_failure`` / ``_mark_status`` so the retry sweeper can
    drive subsequent attempts. Returns ``True`` on success, ``False``
    otherwise — never raises.

    Guardrails:

    * Muted alerts → ``delivery_status="suppressed"``, no POST (FR-021).
    * Below-threshold alerts → ``delivery_status="n/a"``, no POST
      (FR-017).  The below-threshold filter is applied upstream in
      :func:`deliver`; callers that bypass that (e.g. the retry
      sweeper) should not be sweeping below-threshold rows.
    * Already-sent or already-terminal alerts → no POST (FR-022 dedup
      guarantee — one alert instance ⇒ at most one successful HA push).
    """
    now = _utcnow()

    # Dedup: never re-POST if this alert has already been delivered or
    # has already exhausted its retry budget. The sweeper should also
    # filter these out at its SELECT step, but we enforce it here as
    # a belt-and-suspenders check (FR-022).
    if alert.delivery_status in ("sent", "terminal"):
        return alert.delivery_status == "sent"

    # Mute check — recorded on the alert row; no retry scheduled.
    try:
        if await _is_alert_muted(session, alert, now):
            _mark_status(alert, "suppressed")
            logger.info(
                "notification.ha.suppressed",
                extra={
                    "event": "notification.ha.suppressed",
                    "sink_id": sink.id,
                    "alert_id": alert.id,
                },
            )
            return False
    except Exception:  # noqa: BLE001 — mute lookup must not crash delivery
        logger.exception(
            "notification.ha.mute_lookup_failed",
            extra={
                "event": "notification.ha.mute_lookup_failed",
                "sink_id": sink.id,
                "alert_id": alert.id,
            },
        )

    # Severity threshold — recorded on the alert row; no retry scheduled.
    if not _meets_cutoff(sink.min_severity, alert.severity):
        _mark_status(alert, "n/a")
        return False

    # Resolve connection. A mis-configured sink is a failure — record it
    # and let the sweeper retry once, but log a warning so the admin can
    # notice a broken wiring.
    conn = await _load_ha_connection(session, sink)
    if conn is None:
        logger.warning(
            "notification.ha.connection_missing",
            extra={
                "event": "notification.ha.connection_missing",
                "sink_id": sink.id,
                "alert_id": alert.id,
            },
        )
        _record_failure(alert, now)
        return False

    t0 = time.monotonic()
    payload = _ha_payload(alert)
    try:
        # The ha_client wraps httpx for the real HA REST endpoints. Its
        # timeout is settings.ha_request_timeout_seconds (10 s default);
        # we clamp to 5 s for notify calls to match the existing webhook
        # path's feel. This is achieved by overriding the timeout on
        # the single call below when httpx is mocked in tests — the
        # call_notify helper itself uses the config timeout.
        await _call_notify_with_timeout(conn, sink.endpoint, payload)
    except HAAuthError as exc:
        # Auth errors exhaust the retry budget on their own; the
        # ha_connection_health rule will also flag the root cause to
        # the admin so the terminal recommendation is not the admin's
        # only signal. Record as a normal failure — the sweeper flips
        # to terminal after the 4th attempt either way.
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "notification.ha.delivery_failed",
            extra={
                "event": "notification.ha.delivery_failed",
                "sink_id": sink.id,
                "alert_id": alert.id,
                "error_class": "auth_failure",
                "latency_ms": latency_ms,
                "error": str(exc),
            },
        )
        _record_failure(alert, now)
        return False
    except (HAUnreachableError, HAUnexpectedPayloadError, HAClientError) as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "notification.ha.delivery_failed",
            extra={
                "event": "notification.ha.delivery_failed",
                "sink_id": sink.id,
                "alert_id": alert.id,
                "error_class": getattr(exc, "error_class", "unknown"),
                "latency_ms": latency_ms,
                "error": str(exc),
            },
        )
        _record_failure(alert, now)
        return False
    except Exception as exc:  # noqa: BLE001 — must never escape
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.exception(
            "notification.ha.delivery_failed",
            extra={
                "event": "notification.ha.delivery_failed",
                "sink_id": sink.id,
                "alert_id": alert.id,
                "error_class": "unknown",
                "latency_ms": latency_ms,
                "error": str(exc),
            },
        )
        _record_failure(alert, now)
        return False

    latency_ms = int((time.monotonic() - t0) * 1000)
    _record_success(alert, now)
    logger.info(
        "notification.ha.delivered",
        extra={
            "event": "notification.ha.delivered",
            "sink_id": sink.id,
            "alert_id": alert.id,
            "service": sink.endpoint,
            "latency_ms": latency_ms,
        },
    )
    return True


async def _call_notify_with_timeout(
    conn: HomeAssistantConnection, service: str, payload: dict[str, Any]
) -> Any:
    """Invoke ``ha_client.call_notify`` with a clamped 5 s timeout.

    The existing HA client reads its timeout from
    ``settings.ha_request_timeout_seconds`` (default 10). Notifications
    should be snappier — match the webhook sink's 5 s ceiling so a
    partial HA outage does not block the cycle.

    Implementation note: we use a local asyncio.wait_for rather than
    rewiring the client's httpx layer. The client's inner httpx timeout
    still applies; wait_for provides the outer cap.
    """
    import asyncio

    return await asyncio.wait_for(
        ha_client.call_notify(conn, service, payload),
        timeout=_HA_NOTIFY_TIMEOUT_SECONDS,
    )


# ── Webhook test (F4.5) — preserved exactly ────────────────────────────


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
