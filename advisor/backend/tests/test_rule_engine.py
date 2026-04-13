"""Tests for the rule engine's run_cycle() orchestration.

These tests use a stub Rule whose result set is controlled per-cycle to
assert:

* A single result produces one active alert per cycle.
* Re-running with the same condition does not duplicate rows (dedup).
* Clearing the condition auto-resolves with resolution_source='auto'.
* A re-fire inside the 10-minute cool-down is blocked; after cool-down it
  creates a new instance.
* The sustained-window streak filter drops short spikes for rules with a
  non-zero ``sustained_window``.
* Resolved rows older than 30 days are pruned each cycle.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.alert import Alert
from app.services import rule_engine
from app.services.rule_engine import _STREAKS, run_cycle
from app.services.rules.base import Rule, RuleContext, RuleResult

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StubRule(Rule):
    """A rule whose .evaluate() return value is mutated between cycles."""

    id = "stub_rule"
    name = "Stub test rule"
    severity = "warning"
    sustained_window = timedelta(0)

    def __init__(self):
        self.next_results: list[RuleResult] = []

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        return list(self.next_results)


@pytest_asyncio.fixture
async def engine_env(monkeypatch):
    """Spin up a fresh in-memory DB, patch rule_engine to use it, clear
    the in-memory streak map, and yield (session_factory, stub_rule, app)."""
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

    stub = StubRule()

    # Patch the engine module's globals so run_cycle uses our stub and DB.
    monkeypatch.setattr(rule_engine, "RULES", [stub])
    monkeypatch.setattr(rule_engine, "async_session", session_factory)
    # Ollama probe would try to hit HTTP — replace with AsyncMock.
    monkeypatch.setattr(
        rule_engine, "_probe_ollama", AsyncMock(return_value=True)
    )

    # Clear global streak dict so tests don't leak state into each other.
    _STREAKS.clear()

    # Minimal app-like object: run_cycle only reads app.state.container_state.
    app = SimpleNamespace(state=SimpleNamespace(container_state={}))

    yield session_factory, stub, app

    _STREAKS.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _sample_result() -> RuleResult:
    return RuleResult(
        target_type="device",
        target_id=42,
        message="stub breach on device 42",
    )


async def _count_alerts(session_factory, **filters) -> int:
    async with session_factory() as session:
        q = select(Alert)
        for k, v in filters.items():
            q = q.where(getattr(Alert, k) == v)
        rows = (await session.execute(q)).scalars().all()
        return len(rows)


# ── (a) full cycle creates one alert per result ────────────────────────


@pytest.mark.asyncio
async def test_run_cycle_creates_alert_from_rule_result(engine_env):
    session_factory, stub, app = engine_env
    stub.next_results = [_sample_result()]

    stats = await run_cycle(app)

    assert stats["alerts_created"] == 1
    assert stats["rules_evaluated"] == 1

    async with session_factory() as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
    assert len(alerts) == 1
    a = alerts[0]
    assert a.state == "active"
    assert a.rule_id == "stub_rule"
    assert a.target_type == "device"
    assert a.target_id == 42
    assert a.severity == "warning"
    assert a.source == "rule"
    assert a.suppressed is False
    assert a.message == "stub breach on device 42"


# ── (b) idempotent: second cycle with same condition no duplicate ──────


@pytest.mark.asyncio
async def test_run_cycle_dedupes_second_cycle(engine_env):
    session_factory, stub, app = engine_env
    stub.next_results = [_sample_result()]

    first = await run_cycle(app)
    second = await run_cycle(app)

    assert first["alerts_created"] == 1
    assert second["alerts_created"] == 0

    total = await _count_alerts(session_factory)
    active = await _count_alerts(session_factory, state="active")
    assert total == 1
    assert active == 1


# ── (c) clearing the condition auto-resolves the alert ─────────────────


@pytest.mark.asyncio
async def test_run_cycle_auto_resolves_cleared_condition(engine_env):
    session_factory, stub, app = engine_env

    stub.next_results = [_sample_result()]
    await run_cycle(app)

    # Now the condition clears.
    stub.next_results = []
    stats = await run_cycle(app)

    assert stats["alerts_resolved"] == 1

    async with session_factory() as session:
        alert = (await session.execute(select(Alert))).scalar_one()
    assert alert.state == "resolved"
    assert alert.resolved_at is not None
    assert alert.resolution_source == "auto"


# ── (d) / (e) 10-minute cool-down ──────────────────────────────────────


@pytest.mark.asyncio
async def test_cooldown_blocks_refire_within_10_minutes(engine_env, monkeypatch):
    session_factory, stub, app = engine_env

    # Cycle 1: breach at T=0, alert created.
    stub.next_results = [_sample_result()]
    await run_cycle(app)

    # Cycle 2: condition clears → alert resolves.
    stub.next_results = []
    await run_cycle(app)

    # Cycle 3: breach returns 1 minute later → still inside 10-min cool-down.
    # Advance _utcnow by 1 minute so cool-down compares against real times.
    fake_now = _now() + timedelta(minutes=1)
    monkeypatch.setattr(rule_engine, "_utcnow", lambda: fake_now)
    stub.next_results = [_sample_result()]
    stats = await run_cycle(app)

    assert stats["alerts_created"] == 0, "cool-down should block the refire"

    total = await _count_alerts(session_factory)
    assert total == 1  # still just the original (now resolved) row


@pytest.mark.asyncio
async def test_cooldown_allows_refire_after_10_minutes(engine_env, monkeypatch):
    session_factory, stub, app = engine_env

    stub.next_results = [_sample_result()]
    await run_cycle(app)

    stub.next_results = []
    await run_cycle(app)

    # Advance past the cool-down window (11 minutes).
    fake_now = _now() + timedelta(minutes=11)
    monkeypatch.setattr(rule_engine, "_utcnow", lambda: fake_now)
    stub.next_results = [_sample_result()]
    stats = await run_cycle(app)

    assert stats["alerts_created"] == 1, "cool-down expired — refire allowed"

    total = await _count_alerts(session_factory)
    assert total == 1  # re-activated the resolved row (no duplicates)
    active = await _count_alerts(session_factory, state="active")
    assert active == 1


# ── (f) sustained-window streak drops spikes ───────────────────────────


@pytest.mark.asyncio
async def test_sustained_window_drops_short_spike(engine_env, monkeypatch):
    session_factory, stub, app = engine_env

    # Give the stub a 5-minute sustained window.
    stub.sustained_window = timedelta(minutes=5)

    start = _now()

    # Cycle 1 at T=0: breach observed — streak starts, no alert yet.
    monkeypatch.setattr(rule_engine, "_utcnow", lambda: start)
    stub.next_results = [_sample_result()]
    stats = await run_cycle(app)
    assert stats["alerts_created"] == 0

    # Cycle 2 at T=+1 minute: still breaching but streak age < 5 min → drop.
    monkeypatch.setattr(
        rule_engine, "_utcnow", lambda: start + timedelta(minutes=1)
    )
    stub.next_results = [_sample_result()]
    stats = await run_cycle(app)
    assert stats["alerts_created"] == 0

    # Cycle 3 at T=+6 minutes: streak survived the window → fire.
    monkeypatch.setattr(
        rule_engine, "_utcnow", lambda: start + timedelta(minutes=6)
    )
    stub.next_results = [_sample_result()]
    stats = await run_cycle(app)
    assert stats["alerts_created"] == 1

    total = await _count_alerts(session_factory)
    assert total == 1


# ── (g) 30-day retention pruning ───────────────────────────────────────


@pytest.mark.asyncio
async def test_old_resolved_alerts_pruned(engine_env):
    session_factory, stub, app = engine_env

    now = _now()
    # Manually insert a resolved alert 31 days old.
    async with session_factory() as session:
        old = Alert(
            rule_id="stub_rule",
            target_type="device",
            target_id=99,
            severity="warning",
            message="old",
            created_at=now - timedelta(days=31),
            state="resolved",
            resolved_at=now - timedelta(days=31),
            resolution_source="auto",
            source="rule",
            suppressed=False,
        )
        # And one fresh resolved alert — should survive.
        fresh = Alert(
            rule_id="stub_rule",
            target_type="device",
            target_id=100,
            severity="warning",
            message="fresh",
            created_at=now - timedelta(hours=1),
            state="resolved",
            resolved_at=now - timedelta(hours=1),
            resolution_source="auto",
            source="rule",
            suppressed=False,
        )
        session.add(old)
        session.add(fresh)
        await session.commit()

    # Run an empty cycle (no breaches) — should prune only the old one.
    stub.next_results = []
    stats = await run_cycle(app)
    assert stats["alerts_pruned"] == 1

    async with session_factory() as session:
        remaining = (await session.execute(select(Alert))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].target_id == 100


# ── US5: notification hot-reload behaviour ─────────────────────────────


class TestNotificationHotReload:
    """FR-025: enabling/disabling a NotificationSink takes effect on the
    next rule-engine cycle without needing a process restart."""

    @pytest.mark.asyncio
    async def test_new_alert_triggers_deliver(self, engine_env, monkeypatch):
        from app.models.notification_sink import NotificationSink
        from app.services import notification_sender

        session_factory, stub, app = engine_env
        stub.next_results = [_sample_result()]

        # Insert an enabled sink that accepts warnings.
        async with session_factory() as session:
            session.add(
                NotificationSink(
                    type="home_assistant",
                    name="ha",
                    enabled=True,
                    endpoint="http://ha/api/webhook/t",
                    min_severity="warning",
                )
            )
            await session.commit()

        recorded = AsyncMock(return_value=(1, 1))
        monkeypatch.setattr(notification_sender, "deliver", recorded)

        stats = await run_cycle(app)
        assert stats["alerts_created"] == 1
        assert stats["ha_notifications_sent"] == 1
        assert stats["ha_notifications_failed"] == 0
        assert recorded.await_count == 1

        _, alert = recorded.await_args.args
        assert alert.rule_id == "stub_rule"
        assert alert.target_id == 42
        assert alert.suppressed is False

    @pytest.mark.asyncio
    async def test_suppressed_alert_skipped_by_deliver(
        self, engine_env, monkeypatch
    ):
        from app.models.notification_sink import NotificationSink
        from app.models.rule_mute import RuleMute
        from app.services import notification_sender

        session_factory, stub, app = engine_env
        stub.next_results = [_sample_result()]

        now = _now()
        async with session_factory() as session:
            session.add(
                NotificationSink(
                    type="home_assistant",
                    name="ha",
                    enabled=True,
                    endpoint="http://ha/api/webhook/t",
                    min_severity="warning",
                )
            )
            session.add(
                RuleMute(
                    rule_id="stub_rule",
                    target_type="device",
                    target_id=42,
                    created_at=now,
                    expires_at=now + timedelta(hours=1),
                    note="muted for test",
                )
            )
            await session.commit()

        recorded = AsyncMock(return_value=(1, 1))
        monkeypatch.setattr(notification_sender, "deliver", recorded)

        stats = await run_cycle(app)

        assert stats["alerts_suppressed"] == 1
        assert stats["alerts_created"] == 0
        assert stats["ha_notifications_sent"] == 0
        assert stats["ha_notifications_failed"] == 0
        # A suppressed alert must never be handed to the delivery layer.
        assert recorded.await_count == 0

    @pytest.mark.asyncio
    async def test_sink_toggle_hot_reload(self, engine_env, monkeypatch):
        from app.models.notification_sink import NotificationSink
        from app.services import notification_sender

        session_factory, stub, app = engine_env

        async with session_factory() as session:
            sink = NotificationSink(
                type="home_assistant",
                name="ha",
                enabled=True,
                endpoint="http://ha/api/webhook/t",
                min_severity="warning",
            )
            session.add(sink)
            await session.commit()
            await session.refresh(sink)
            sink_id = sink.id

        recorded = AsyncMock(return_value=(1, 1))
        monkeypatch.setattr(notification_sender, "deliver", recorded)

        # Cycle 1: enabled sink receives the alert.
        stub.next_results = [_sample_result()]
        await run_cycle(app)
        assert recorded.await_count == 1

        # Now disable the sink directly via the DB and reset the mock.
        async with session_factory() as session:
            row = await session.get(NotificationSink, sink_id)
            row.enabled = False
            await session.commit()

        recorded.reset_mock()

        # Cycle 2: emit a RuleResult against a different target so we bypass
        # the (rule_id, target) dedup guard and actually create a new alert.
        stub.next_results = [
            RuleResult(
                target_type="device",
                target_id=77,
                message="different target to bypass dedup",
            )
        ]
        stats = await run_cycle(app)
        assert stats["alerts_created"] == 1, (
            "a new alert should still be created — we just don't deliver it"
        )
        assert recorded.await_count == 0, (
            "disabled sink must not receive the new alert in the very next cycle"
        )
