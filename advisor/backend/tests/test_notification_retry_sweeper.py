"""Tests for notification_retry_sweeper (T059).

Covers the sweep pass invoked from ``ha_poller.run_cycle``:

1. Selection — only ``delivery_status='failed'`` rows whose
   ``delivery_next_attempt_at`` has matured are picked up; ``sent``,
   ``terminal``, ``suppressed``, ``n/a``, and ``pending`` rows are
   never swept.
2. Backoff progression — successive sweeps (with mocked 5xx) advance
   the attempt count and schedule the next attempt at +30 s / +60 s /
   +120 s / +240 s per research R6. After four failed attempts the
   sweeper promotes the alert to ``terminal`` and inserts a
   ``notification_delivery_failure`` recommendation.
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
from app.security import encrypt_token
from app.services import ha_client, notification_retry_sweeper
from app.services.ha_client import HAUnreachableError

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Expected delays keyed by the attempt count AFTER the sweep's increment
# (matches ``notification_sender._RETRY_BACKOFF_SECONDS`` and T059 spec):
#
#   count becomes 2 → +30 s until attempt 3
#   count becomes 3 → +60 s until attempt 4
#   count becomes 4 → +120 s grace until terminal (though the sweeper
#                     usually promotes earlier via the pre-check)
_BACKOFF = {2: 30, 3: 60, 4: 120}
_TOL = 5  # ±5 s tolerance for scheduling math


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
        session.add(
            HomeAssistantConnection(
                id=1,
                base_url="http://homeassistant.local:8123",
                token_ciphertext=encrypt_token("llat_test_token_ABCD"),
            )
        )
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


async def _insert_failed_alert(
    session,
    *,
    attempt_count: int = 1,
    next_attempt_at: datetime | None = None,
    status: str = "failed",
) -> Alert:
    alert = Alert(
        severity="critical",
        message="thread_border_router_offline: Kitchen HomePod",
        created_at=_now(),
        rule_id="thread_border_router_offline",
        target_type="device",
        target_id=42,
        state="active",
        source="rule",
        suppressed=False,
        delivery_status=status,
        delivery_attempt_count=attempt_count,
        delivery_last_attempt_at=_now() - timedelta(seconds=30),
        delivery_next_attempt_at=next_attempt_at,
    )
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert


# ── Happy selection ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_selection_picks_past_due_failed_only(db, monkeypatch):
    """3 failed alerts: past, now, future. Only the first two are swept."""
    past = await _insert_failed_alert(
        db, attempt_count=1, next_attempt_at=_now() - timedelta(seconds=5)
    )
    at_now = await _insert_failed_alert(
        db, attempt_count=1, next_attempt_at=_now()
    )
    future = await _insert_failed_alert(
        db, attempt_count=1, next_attempt_at=_now() + timedelta(seconds=60)
    )

    # Also a `sent` and a `terminal` row — never swept.
    sent = await _insert_failed_alert(
        db,
        attempt_count=1,
        next_attempt_at=_now() - timedelta(seconds=5),
        status="sent",
    )
    terminal = await _insert_failed_alert(
        db,
        attempt_count=4,
        next_attempt_at=_now() - timedelta(seconds=5),
        status="terminal",
    )
    suppressed = await _insert_failed_alert(
        db,
        attempt_count=0,
        next_attempt_at=_now() - timedelta(seconds=5),
        status="suppressed",
    )
    na = await _insert_failed_alert(
        db,
        attempt_count=0,
        next_attempt_at=_now() - timedelta(seconds=5),
        status="n/a",
    )

    call_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ha_client, "call_notify", call_mock)

    await notification_retry_sweeper.sweep(db)

    # Past + at_now are swept (success → sent).
    await db.refresh(past)
    await db.refresh(at_now)
    await db.refresh(future)
    await db.refresh(sent)
    await db.refresh(terminal)
    await db.refresh(suppressed)
    await db.refresh(na)

    assert past.delivery_status == "sent"
    assert at_now.delivery_status == "sent"
    assert future.delivery_status == "failed"  # still scheduled future
    assert sent.delivery_status == "sent"  # was already sent
    assert terminal.delivery_status == "terminal"
    assert suppressed.delivery_status == "suppressed"
    assert na.delivery_status == "n/a"

    # Exactly two POSTs.
    assert call_mock.await_count == 2


# ── Status filter — nothing but failed w/ past-due schedule gets swept ─


@pytest.mark.asyncio
async def test_status_filter_skips_non_failed(db, monkeypatch):
    for status in ("sent", "terminal", "suppressed", "n/a", "pending"):
        await _insert_failed_alert(
            db,
            attempt_count=1,
            next_attempt_at=_now() - timedelta(seconds=30),
            status=status,
        )

    call_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ha_client, "call_notify", call_mock)

    stats = await notification_retry_sweeper.sweep(db)
    assert stats["picked"] == 0
    assert call_mock.await_count == 0


# ── Backoff progression — 30 / 60 / 120 then terminal ──────────────────


@pytest.mark.asyncio
async def test_backoff_progression_to_terminal(db, monkeypatch):
    """Four failed sweeps advance the backoff ladder, then terminal.

    Delay sequence after each failure (research R6, keyed by attempt
    count BEFORE the increment — "Attempt N delay after previous
    failure"):

    * After attempt 1 failed (count was 0) → +30 s to attempt 2
    * After attempt 2 failed (count was 1) → +60 s to attempt 3
    * After attempt 3 failed (count was 2) → +120 s to attempt 4
    * After attempt 4 failed (count was 3) → terminal (no schedule)
    """
    fail_mock = AsyncMock(side_effect=HAUnreachableError("HA down"))
    monkeypatch.setattr(ha_client, "call_notify", fail_mock)

    # Seed at attempt 1 already attempted (count=1) and scheduled past-due.
    alert = await _insert_failed_alert(
        db,
        attempt_count=1,
        next_attempt_at=_now() - timedelta(seconds=5),
    )

    # Sweep 1 — runs attempt 2. Fails. count → 2, next ≈ +30 s per
    # _RETRY_BACKOFF_SECONDS[2] = 30 (T059 asserts this value).
    await notification_retry_sweeper.sweep(db)
    await db.refresh(alert)
    assert alert.delivery_status == "failed"
    assert alert.delivery_attempt_count == 2
    _assert_next_attempt_in(alert, _BACKOFF[2])

    # Sweep 2 — runs attempt 3, fails. count → 3, next ≈ +120 s.
    alert.delivery_next_attempt_at = _now() - timedelta(seconds=1)
    await db.commit()
    await notification_retry_sweeper.sweep(db)
    await db.refresh(alert)
    assert alert.delivery_status == "failed"
    assert alert.delivery_attempt_count == 3
    _assert_next_attempt_in(alert, _BACKOFF[3])

    # Sweep 3 — runs attempt 4, fails. count → 4, no schedule. The
    # sweeper catches the terminal condition in the same pass.
    alert.delivery_next_attempt_at = _now() - timedelta(seconds=1)
    await db.commit()
    await notification_retry_sweeper.sweep(db)
    await db.refresh(alert)
    assert alert.delivery_status == "terminal"
    assert alert.delivery_attempt_count == 4

    # Recommendation row exists.
    rec = (
        await db.execute(
            select(Alert).where(
                Alert.rule_id == "notification_delivery_failure",
                Alert.target_id == alert.id,
            )
        )
    ).scalar_one_or_none()
    assert rec is not None


def _assert_next_attempt_in(alert: Alert, seconds: int) -> None:
    """Assert delivery_next_attempt_at is ≈ now + ``seconds`` (±_TOL)."""
    assert alert.delivery_next_attempt_at is not None
    now = _now()
    # The value may be naive (sqlite) or tz-aware (postgres); normalise.
    scheduled = alert.delivery_next_attempt_at
    if scheduled.tzinfo is not None:
        scheduled = scheduled.astimezone(timezone.utc).replace(tzinfo=None)
    delta = (scheduled - now).total_seconds()
    assert abs(delta - seconds) <= _TOL, (
        f"expected next attempt in {seconds}s (±{_TOL}s), got {delta:.1f}s"
    )
