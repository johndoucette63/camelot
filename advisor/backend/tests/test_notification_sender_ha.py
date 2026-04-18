"""Tests for the HA-native notify branch of notification_sender (T058).

Covers the feature-016 / US-3 delivery path — the branch of
``notification_sender.deliver`` that targets HA's
``/api/services/notify/<service>`` via ``ha_client.call_notify``. The
test mocks the client at the module boundary so no real HA instance is
needed, and asserts that the delivery state machine on the alert row
advances correctly.

Scenarios:

1. Success → ``delivery_status="sent"``, ``delivery_attempt_count >=1``,
   exactly one call to ``ha_client.call_notify`` observed.
2. Four failures in a row (simulated by repeatedly calling the sender
   directly — no scheduler) → the row advances ``failed`` -> ``failed``
   -> ``failed`` -> ``failed``; the retry sweeper then promotes it to
   ``terminal`` and inserts a ``notification_delivery_failure``
   recommendation row.
3. Below-threshold alert (info when sink requires critical) →
   ``delivery_status="n/a"`` and zero calls to ``call_notify``.
4. Muted alert (active RuleMute covers the (rule, target) pair) →
   ``delivery_status="suppressed"`` and zero calls to ``call_notify``.
5. Dedup idempotence — a second call to ``deliver`` for an already-sent
   alert does NOT POST again (FR-022).
6. Burst coalesce (FR-022 + SC-007) — ten distinct alert instances for
   the same ``(rule_id, target_id)`` pair yield exactly ten POSTs (one
   per alert_id, no cross-instance merge and no silent drop).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.alert import Alert
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.notification_sink import NotificationSink
from app.models.rule_mute import RuleMute
from app.security import encrypt_token
from app.services import ha_client, notification_retry_sweeper, notification_sender
from app.services.ha_client import HAUnreachableError

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        # Seed a configured HA connection so the sink can resolve it.
        session.add(
            HomeAssistantConnection(
                id=1,
                base_url="http://homeassistant.local:8123",
                token_ciphertext=encrypt_token("llat_test_token_ABCD"),
            )
        )
        # Seed a single HA-native sink: critical threshold, enabled,
        # bare notify-service suffix.
        session.add(
            NotificationSink(
                type="home_assistant",
                name="Phone (HA push)",
                enabled=True,
                endpoint="mobile_app_pixel9",
                min_severity="critical",
                home_assistant_id=1,
            )
        )
        await session.commit()
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _insert_alert(session, **overrides) -> Alert:
    """Insert a default critical-severity alert, optionally overridden."""
    defaults = {
        "severity": "critical",
        "message": "thread_border_router_offline: Kitchen HomePod",
        "created_at": _now(),
        "rule_id": "thread_border_router_offline",
        "target_type": "device",
        "target_id": 42,
        "state": "active",
        "source": "rule",
        "suppressed": False,
    }
    defaults.update(overrides)
    alert = Alert(**defaults)
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert


# ── 1. Success path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_sets_sent_and_increments_count(db, monkeypatch):
    alert = await _insert_alert(db)
    call_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ha_client, "call_notify", call_mock)

    attempted, succeeded = await notification_sender.deliver(db, alert)
    await db.commit()
    await db.refresh(alert)

    assert attempted == 1
    assert succeeded == 1
    assert alert.delivery_status == "sent"
    assert alert.delivery_attempt_count >= 1
    assert alert.delivery_last_attempt_at is not None
    assert alert.delivery_next_attempt_at is None
    assert call_mock.await_count == 1

    # Payload shape — research R7.
    _conn_arg, service_arg, payload_arg = call_mock.await_args.args
    assert service_arg == "mobile_app_pixel9"
    assert payload_arg["title"].startswith("Camelot:")
    assert payload_arg["message"] == alert.message
    assert payload_arg["data"]["severity"] == "critical"
    assert payload_arg["data"]["alert_id"] == alert.id


# ── 2. Four failures + sweeper promotion to terminal ───────────────────


@pytest.mark.asyncio
async def test_four_failures_then_sweeper_promotes_terminal(db, monkeypatch):
    alert = await _insert_alert(db)

    # Every call_notify raises HAUnreachableError (simulating 5xx / timeout).
    fail_mock = AsyncMock(side_effect=HAUnreachableError("HA down"))
    monkeypatch.setattr(ha_client, "call_notify", fail_mock)

    # Attempt 1 — the initial send (from deliver()). After the fail
    # count is 1 and the next retry is scheduled (per R6 the delay
    # from attempt 1's failure to attempt 2 is 30 s).
    await notification_sender.deliver(db, alert)
    await db.commit()
    await db.refresh(alert)
    assert alert.delivery_status == "failed"
    assert alert.delivery_attempt_count == 1
    assert alert.delivery_next_attempt_at is not None

    # Drive attempts 2-4 via the retry sweeper. Backdate the schedule
    # each time so the sweeper picks the row up without real sleeps.
    def _backdate():
        alert.delivery_next_attempt_at = _now() - timedelta(seconds=1)

    _backdate()
    await db.commit()
    await notification_retry_sweeper.sweep(db)
    await db.refresh(alert)
    assert alert.delivery_status == "failed"
    assert alert.delivery_attempt_count == 2

    _backdate()
    await db.commit()
    await notification_retry_sweeper.sweep(db)
    await db.refresh(alert)
    assert alert.delivery_status == "failed"
    assert alert.delivery_attempt_count == 3

    _backdate()
    await db.commit()
    await notification_retry_sweeper.sweep(db)
    await db.refresh(alert)
    # After the 4th failed attempt the sweeper promotes to terminal
    # because the backoff table tops out at attempt=4 (delivery helper
    # clears delivery_next_attempt_at) and the sweeper catches that.
    assert alert.delivery_status == "terminal"
    assert alert.delivery_attempt_count == 4

    # A `notification_delivery_failure` recommendation now exists.
    rec = (
        await db.execute(
            select(Alert).where(
                Alert.rule_id == "notification_delivery_failure",
                Alert.target_id == alert.id,
            )
        )
    ).scalar_one_or_none()
    assert rec is not None
    assert rec.severity == "warning"
    assert f"Alert #{alert.id}" in rec.message


# ── 3. Below-threshold alert → n/a, no POST ────────────────────────────


@pytest.mark.asyncio
async def test_below_threshold_is_na_and_no_post(db, monkeypatch):
    alert = await _insert_alert(db, severity="info")
    call_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ha_client, "call_notify", call_mock)

    attempted, succeeded = await notification_sender.deliver(db, alert)
    await db.commit()
    await db.refresh(alert)

    assert attempted == 0
    assert succeeded == 0
    assert alert.delivery_status == "n/a"
    assert call_mock.await_count == 0


# ── 4. Muted alert → suppressed, no POST ───────────────────────────────


@pytest.mark.asyncio
async def test_muted_alert_is_suppressed_and_no_post(db, monkeypatch):
    alert = await _insert_alert(db)

    # Active mute covering the (rule_id, target_type, target_id) tuple.
    db.add(
        RuleMute(
            rule_id=alert.rule_id,
            target_type=alert.target_type,
            target_id=alert.target_id,
            created_at=_now(),
            expires_at=_now() + timedelta(hours=1),
            note="test mute",
        )
    )
    await db.commit()

    call_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ha_client, "call_notify", call_mock)

    await notification_sender.deliver(db, alert)
    await db.commit()
    await db.refresh(alert)

    assert alert.delivery_status == "suppressed"
    assert call_mock.await_count == 0


# ── 5. Dedup — second call does not re-POST ────────────────────────────


@pytest.mark.asyncio
async def test_dedup_second_call_does_not_post_again(db, monkeypatch):
    alert = await _insert_alert(db)
    call_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ha_client, "call_notify", call_mock)

    await notification_sender.deliver(db, alert)
    await db.commit()
    # Second call — the dedup guard in _deliver_one_ha short-circuits.
    await notification_sender.deliver(db, alert)
    await db.commit()
    await db.refresh(alert)

    assert alert.delivery_status == "sent"
    assert call_mock.await_count == 1


# ── 6. Burst coalesce (FR-022 / SC-007) ────────────────────────────────


@pytest.mark.asyncio
async def test_burst_coalesce_one_post_per_alert_instance(db, monkeypatch):
    """Ten alert instances for the same (rule_id, target_id) pair within
    60 s of simulated time yield exactly ten POSTs — one per distinct
    alert_id.

    FR-022 guarantees at most one POST per alert_id (the per-alert
    ``delivery_status`` dedup). Cross-instance merging (one POST for
    ten alerts) is NOT the FR-022 semantics — each alert instance is a
    separate record and receives its own delivery. The test asserts
    the more conservative "no merge, no drop" shape.
    """
    call_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ha_client, "call_notify", call_mock)

    alerts: list[Alert] = []
    for _ in range(10):
        alerts.append(await _insert_alert(db))

    for alert in alerts:
        await notification_sender.deliver(db, alert)
    await db.commit()

    assert call_mock.await_count == 10
    # And each alert landed in `sent` state.
    for alert in alerts:
        await db.refresh(alert)
        assert alert.delivery_status == "sent"
