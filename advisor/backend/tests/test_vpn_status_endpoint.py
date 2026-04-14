"""Tests for the GET /vpn-status endpoint state-precedence logic.

Covers each of the six states + the precedence rule
(AUTO_STOPPED > LEAK_DETECTED > WATCHDOG_DOWN > PROBE_UNREACHABLE > OK > UNKNOWN).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.alert import Alert
from app.routers import vpn as vpn_router
from app.services.rules import vpn_leak as vpn_leak_module

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_utc(dt: datetime) -> str:
    return dt.isoformat() + "Z"


@pytest_asyncio.fixture
async def env(monkeypatch):
    """Fresh DB + clean module-level probe state per test."""
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
    monkeypatch.setattr(vpn_router, "async_session", session_factory)

    # Reset module state to "no probe yet"
    vpn_leak_module._LATEST_PROBE.update(
        {"observed_ip": None, "status": "unknown", "checked_at": None, "error": None}
    )

    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _set_probe(*, status: str, observed_ip: str | None, age_seconds: int = 30, error: str | None = None):
    """Mutate the module-level probe state to simulate a recent probe."""
    checked_at = _utcnow() - timedelta(seconds=age_seconds)
    vpn_leak_module._LATEST_PROBE.update(
        {
            "observed_ip": observed_ip,
            "status": status,
            "checked_at": _iso_utc(checked_at),
            "error": error,
        }
    )


async def _insert_alert(session_factory, *, rule_id: str, state: str = "active"):
    async with session_factory() as session:
        session.add(
            Alert(
                severity="critical",
                message=f"test alert for {rule_id}",
                rule_id=rule_id,
                target_type="service",
                target_id=0,
                state=state,
                source="rule",
                suppressed=False,
            )
        )
        await session.commit()


# ── UNKNOWN: no probe yet ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_state_unknown_when_no_probe(env):
    resp = await vpn_router.get_vpn_status()
    assert resp["state"] == "UNKNOWN"
    assert resp["observed_ip"] is None
    assert resp["last_probe_at"] is None
    assert resp["active_alert_id"] is None


# ── OK: recent green probe, no alerts ───────────────────────────────────


@pytest.mark.asyncio
async def test_state_ok_when_recent_probe_no_alerts(env):
    _set_probe(status="ok", observed_ip="181.41.206.98", age_seconds=30)
    resp = await vpn_router.get_vpn_status()
    assert resp["state"] == "OK"
    assert resp["observed_ip"] == "181.41.206.98"
    assert resp["last_probe_age_seconds"] == 30
    assert "Tunnel up" in resp["message"]


# ── PROBE_UNREACHABLE: probe yellow, no alerts ──────────────────────────


@pytest.mark.asyncio
async def test_state_probe_unreachable_when_yellow(env):
    _set_probe(status="probe_unreachable", observed_ip=None, age_seconds=30, error="ssh timeout")
    resp = await vpn_router.get_vpn_status()
    assert resp["state"] == "PROBE_UNREACHABLE"
    assert "Cannot probe" in resp["message"]


# ── WATCHDOG_DOWN: probe is stale ───────────────────────────────────────


@pytest.mark.asyncio
async def test_state_watchdog_down_when_probe_too_old(env):
    # > 2 × rule_engine_interval_seconds (default 60s) → > 120s → use 200s
    _set_probe(status="ok", observed_ip="181.41.206.98", age_seconds=200)
    resp = await vpn_router.get_vpn_status()
    assert resp["state"] == "WATCHDOG_DOWN"
    assert "watchdog" in resp["message"].lower()


# ── LEAK_DETECTED: active vpn_leak alert ────────────────────────────────


@pytest.mark.asyncio
async def test_state_leak_detected_when_active_alert(env):
    session_factory = env
    _set_probe(status="leak", observed_ip="67.176.27.48", age_seconds=30)
    await _insert_alert(session_factory, rule_id="vpn_leak", state="active")

    resp = await vpn_router.get_vpn_status()
    assert resp["state"] == "LEAK_DETECTED"
    assert resp["active_alert_id"] is not None
    assert "egressing on" in resp["message"]


# ── AUTO_STOPPED: active remediation alert ──────────────────────────────


@pytest.mark.asyncio
async def test_state_auto_stopped_when_remediation_alert(env):
    session_factory = env
    _set_probe(status="leak", observed_ip="67.176.27.48", age_seconds=30)
    # Both alerts present — AUTO_STOPPED has highest precedence
    await _insert_alert(session_factory, rule_id="vpn_leak", state="active")
    await _insert_alert(session_factory, rule_id="vpn_leak:remediation", state="active")

    resp = await vpn_router.get_vpn_status()
    assert resp["state"] == "AUTO_STOPPED"
    assert resp["active_remediation_alert_id"] is not None
    assert "auto-stopped" in resp["message"].lower()


# ── Resolved alerts do not influence state ──────────────────────────────


@pytest.mark.asyncio
async def test_resolved_alerts_do_not_change_state(env):
    session_factory = env
    _set_probe(status="ok", observed_ip="181.41.206.98", age_seconds=30)
    await _insert_alert(session_factory, rule_id="vpn_leak", state="resolved")
    await _insert_alert(session_factory, rule_id="vpn_leak:remediation", state="resolved")

    resp = await vpn_router.get_vpn_status()
    assert resp["state"] == "OK"


# ── Suppressed alerts do not influence state ────────────────────────────


@pytest.mark.asyncio
async def test_suppressed_alerts_do_not_change_state(env):
    session_factory = env
    _set_probe(status="leak", observed_ip="67.176.27.48", age_seconds=30)
    async with session_factory() as session:
        session.add(
            Alert(
                severity="critical",
                message="suppressed",
                rule_id="vpn_leak",
                target_type="service",
                target_id=0,
                state="active",
                source="rule",
                suppressed=True,
            )
        )
        await session.commit()

    resp = await vpn_router.get_vpn_status()
    # Only suppressed leak alert exists → no LEAK_DETECTED gating
    # (matches the engine's normal "ignore suppressed" semantics)
    assert resp["state"] != "LEAK_DETECTED"
