"""Tests for the VPN leak watchdog rule + escalation handling.

Covers:
* Probe success with non-denylist IP → no alert (OK)
* Probe success with denylist IP → critical alert (LEAK)
* Probe unreachable → soft warning, no alert (FR-014)
* Three consecutive leaks → escalation invokes on_escalate exactly once
* on_escalate returns a follow-up RuleResult that becomes a remediation alert
* Remediation success vs failure produces different message text
* Auto-resolve on clear resets the escalation counter
* Module-level _LATEST_PROBE state mirrors the latest cycle
"""
from __future__ import annotations

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
from app.services.rule_engine import (
    _ESCALATION_COUNTS,
    _ESCALATION_FIRED,
    _STREAKS,
    run_cycle,
)
from app.services.rules import vpn_leak as vpn_leak_module
from app.services.rules.vpn_leak import VpnLeakRule

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture
async def engine_env(monkeypatch):
    """Spin up a fresh in-memory DB and patch the engine to use a single
    VpnLeakRule. Reset the in-memory streak / escalation state between
    tests."""
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

    rule = VpnLeakRule()

    monkeypatch.setattr(rule_engine, "RULES", [rule])
    monkeypatch.setattr(rule_engine, "async_session", session_factory)
    monkeypatch.setattr(
        rule_engine, "_probe_ollama", AsyncMock(return_value=True)
    )

    _STREAKS.clear()
    _ESCALATION_COUNTS.clear()
    _ESCALATION_FIRED.clear()
    vpn_leak_module._LATEST_PROBE.update(
        {"observed_ip": None, "status": "unknown", "checked_at": None, "error": None}
    )

    app = SimpleNamespace(state=SimpleNamespace(container_state={}))

    yield session_factory, rule, app

    _STREAKS.clear()
    _ESCALATION_COUNTS.clear()
    _ESCALATION_FIRED.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _patch_probe(monkeypatch, status: str, observed_ip: str | None, error: str | None = None):
    """Replace the SSH probe with a stub returning the given outcome."""
    monkeypatch.setattr(
        vpn_leak_module,
        "_probe_external_ip",
        AsyncMock(return_value=(status, observed_ip, error)),
    )


def _patch_denylist(monkeypatch, ips: set[str]):
    """Override the settings denylist to a controlled set."""
    monkeypatch.setattr(
        vpn_leak_module.settings.__class__,
        "vpn_leak_denylist_ips_set",
        property(lambda _self: ips),
    )


def _patch_remediation(monkeypatch, ok: bool, err: str | None = None):
    """Stub stop_container so escalation tests don't shell out."""
    monkeypatch.setattr(
        vpn_leak_module,
        "stop_container",
        AsyncMock(return_value=(ok, err)),
    )


# ── (a) healthy: non-denylist IP → no alert, status=ok ─────────────────


@pytest.mark.asyncio
async def test_evaluate_ok_when_observed_ip_not_in_denylist(engine_env, monkeypatch):
    session_factory, rule, app = engine_env
    _patch_probe(monkeypatch, "ok", "181.41.206.98")
    _patch_denylist(monkeypatch, {"67.176.27.48"})

    stats = await run_cycle(app)

    assert stats["alerts_created"] == 0
    assert vpn_leak_module._LATEST_PROBE["status"] == "ok"
    assert vpn_leak_module._LATEST_PROBE["observed_ip"] == "181.41.206.98"


# ── (b) leak: denylist hit → one critical alert ─────────────────────────


@pytest.mark.asyncio
async def test_evaluate_emits_alert_when_observed_ip_in_denylist(engine_env, monkeypatch):
    session_factory, rule, app = engine_env
    _patch_probe(monkeypatch, "ok", "67.176.27.48")
    _patch_denylist(monkeypatch, {"67.176.27.48"})

    stats = await run_cycle(app)

    assert stats["alerts_created"] == 1
    assert vpn_leak_module._LATEST_PROBE["status"] == "leak"

    async with session_factory() as session:
        alert = (await session.execute(select(Alert))).scalar_one()
    assert alert.rule_id == "vpn_leak"
    assert alert.severity == "critical"
    assert alert.target_type == "service"
    assert "67.176.27.48" in alert.message


# ── (c) probe unreachable → no alert (soft warning, FR-014) ─────────────


@pytest.mark.asyncio
async def test_evaluate_probe_unreachable_does_not_emit_alert(engine_env, monkeypatch):
    session_factory, rule, app = engine_env
    _patch_probe(monkeypatch, "probe_unreachable", None, error="ssh timeout")
    _patch_denylist(monkeypatch, {"67.176.27.48"})

    stats = await run_cycle(app)

    assert stats["alerts_created"] == 0
    assert vpn_leak_module._LATEST_PROBE["status"] == "probe_unreachable"
    assert vpn_leak_module._LATEST_PROBE["error"] == "ssh timeout"


# ── (d) three consecutive leaks → escalation exactly once ───────────────


@pytest.mark.asyncio
async def test_three_consecutive_leaks_escalate_exactly_once(engine_env, monkeypatch):
    session_factory, rule, app = engine_env
    _patch_probe(monkeypatch, "ok", "67.176.27.48")
    _patch_denylist(monkeypatch, {"67.176.27.48"})
    _patch_remediation(monkeypatch, ok=True)

    # Reduce the threshold to 3 explicitly (matches default but we want the
    # test to be self-contained).
    monkeypatch.setattr(rule, "escalation_threshold", 3)

    # Each cycle re-fires the same leak; cooldown blocks the LEAK alert
    # itself after cycle 1 (resolved-then-refire is what cooldown checks),
    # but the escalation counter is incremented on every result that passes
    # the streak filter (i.e., currently breaching), so we verify counter
    # behavior rather than alert count for the leak rule itself.
    cycle1 = await run_cycle(app)
    cycle2 = await run_cycle(app)
    cycle3 = await run_cycle(app)

    # The leak alert is created once (cycle 1) then deduped on subsequent
    # cycles since the same alert remains active.
    assert cycle1["alerts_created"] >= 1
    # Cycle 3's third strike triggers escalation; the remediation
    # follow-up is also processed as an alert, so cycle3 alerts_created
    # may include the remediation alert.
    assert vpn_leak_module.stop_container.await_count == 1

    # The remediation alert was emitted with a distinct rule_id.
    async with session_factory() as session:
        rem_alerts = (
            await session.execute(
                select(Alert).where(Alert.rule_id == "vpn_leak:remediation")
            )
        ).scalars().all()
    assert len(rem_alerts) == 1
    assert "Auto-stopped" in rem_alerts[0].message
    assert rem_alerts[0].severity == "critical"


# ── (e) escalation does not re-fire on continued breach ─────────────────


@pytest.mark.asyncio
async def test_escalation_does_not_refire_on_continued_breach(engine_env, monkeypatch):
    session_factory, rule, app = engine_env
    _patch_probe(monkeypatch, "ok", "67.176.27.48")
    _patch_denylist(monkeypatch, {"67.176.27.48"})
    _patch_remediation(monkeypatch, ok=True)
    monkeypatch.setattr(rule, "escalation_threshold", 3)

    # Five cycles of continuous leak. Escalation should fire exactly once.
    for _ in range(5):
        await run_cycle(app)

    assert vpn_leak_module.stop_container.await_count == 1


# ── (f) remediation failure surfaces in the message ─────────────────────


@pytest.mark.asyncio
async def test_remediation_failure_surfaces_in_message(engine_env, monkeypatch):
    session_factory, rule, app = engine_env
    _patch_probe(monkeypatch, "ok", "67.176.27.48")
    _patch_denylist(monkeypatch, {"67.176.27.48"})
    _patch_remediation(monkeypatch, ok=False, err="ssh exit 255: connection refused")
    monkeypatch.setattr(rule, "escalation_threshold", 3)

    for _ in range(3):
        await run_cycle(app)

    async with session_factory() as session:
        rem_alert = (
            await session.execute(
                select(Alert).where(Alert.rule_id == "vpn_leak:remediation")
            )
        ).scalar_one()
    assert "FAILED" in rem_alert.message
    assert "ssh exit 255" in rem_alert.message


# ── (g) clear-and-refire resets escalation counter ──────────────────────


@pytest.mark.asyncio
async def test_clear_resets_escalation_counter(engine_env, monkeypatch):
    session_factory, rule, app = engine_env
    _patch_denylist(monkeypatch, {"67.176.27.48"})
    _patch_remediation(monkeypatch, ok=True)
    monkeypatch.setattr(rule, "escalation_threshold", 3)

    # Two leak cycles (counter=2), then clear, then one more leak.
    _patch_probe(monkeypatch, "ok", "67.176.27.48")
    await run_cycle(app)
    await run_cycle(app)

    # Clear the condition (probe returns a non-denylist IP).
    _patch_probe(monkeypatch, "ok", "181.41.206.98")
    await run_cycle(app)

    # Re-arm: leak again.
    _patch_probe(monkeypatch, "ok", "67.176.27.48")
    await run_cycle(app)

    # Counter should have reset on clear, so we're at count=1 now,
    # not 3 — escalation should NOT have fired.
    assert vpn_leak_module.stop_container.await_count == 0
