"""Tests for the Thread-border-router-offline rule (feature 016, T046).

Verifies the rule:

* Emits a critical RuleResult for an offline border router whose
  ha_device_id matches a row in ``devices``.
* Emits nothing for an online border router.
* Logs a warning and emits nothing when a border router has no matching
  ``devices`` row.
* When two border routers exist (one online, one offline), emits
  exactly one result for the offline router.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.device import Device
from app.models.thread_border_router import ThreadBorderRouter
from app.services.rules.base import RuleContext
from app.services.rules.thread_border_router_offline import (
    ThreadBorderRouterOfflineRule,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture
async def rule_env():
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
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _ctx(session: AsyncSession) -> RuleContext:
    return RuleContext(now=_utcnow(), session=session)


async def _seed_router(
    session,
    *,
    ha_device_id: str,
    friendly_name: str,
    online: bool,
    model: str | None = None,
) -> None:
    session.add(
        ThreadBorderRouter(
            ha_device_id=ha_device_id,
            friendly_name=friendly_name,
            model=model,
            online=online,
            attached_device_count=0,
            last_refreshed_at=_utcnow(),
        )
    )
    await session.flush()


async def _seed_device(
    session,
    *,
    ha_device_id: str,
    hostname: str = "hub",
) -> Device:
    device = Device(
        mac_address=None,
        ip_address=None,
        hostname=hostname,
        vendor=None,
        first_seen=_utcnow(),
        last_seen=_utcnow(),
        is_online=True,
        is_known_device=True,
        monitor_offline=True,
        ha_device_id=ha_device_id,
    )
    session.add(device)
    await session.flush()
    return device


# ── (a) offline router + matching device → one critical result ─────────


@pytest.mark.asyncio
async def test_offline_router_with_device_fires(rule_env):
    session = rule_env
    device = await _seed_device(session, ha_device_id="br-1", hostname="kitchen-hub")
    await _seed_router(
        session,
        ha_device_id="br-1",
        friendly_name="HomePod mini — Kitchen",
        online=False,
    )
    await session.commit()

    rule = ThreadBorderRouterOfflineRule()
    results = await rule.evaluate(_ctx(session))

    assert len(results) == 1
    result = results[0]
    assert result.target_type == "device"
    assert result.target_id == device.id
    assert "HomePod mini — Kitchen" in result.message
    assert "offline" in result.message.lower()
    # Severity is declared on the rule class, not the result.
    assert rule.severity == "critical"


# ── (b) online router → nothing emitted ────────────────────────────────


@pytest.mark.asyncio
async def test_online_router_emits_nothing(rule_env):
    session = rule_env
    await _seed_device(session, ha_device_id="br-1", hostname="kitchen-hub")
    await _seed_router(
        session,
        ha_device_id="br-1",
        friendly_name="HomePod mini — Kitchen",
        online=True,
    )
    await session.commit()

    rule = ThreadBorderRouterOfflineRule()
    results = await rule.evaluate(_ctx(session))

    assert results == []


# ── (c) offline router, no matching device → skip + warn ───────────────


@pytest.mark.asyncio
async def test_offline_router_without_device_logs_warning(rule_env, caplog):
    session = rule_env
    await _seed_router(
        session,
        ha_device_id="br-orphan",
        friendly_name="Orphan Router",
        online=False,
    )
    await session.commit()

    rule = ThreadBorderRouterOfflineRule()
    with caplog.at_level(logging.WARNING):
        results = await rule.evaluate(_ctx(session))

    assert results == []
    assert any(
        "br-orphan" in record.getMessage() for record in caplog.records
    ), f"expected a warning mentioning br-orphan; got: {[r.getMessage() for r in caplog.records]}"


# ── (d) two routers, one online + one offline → one result ─────────────


@pytest.mark.asyncio
async def test_mixed_routers_emits_one_result(rule_env):
    session = rule_env
    online_device = await _seed_device(
        session, ha_device_id="br-online", hostname="online-hub"
    )
    offline_device = await _seed_device(
        session, ha_device_id="br-offline", hostname="offline-hub"
    )
    await _seed_router(
        session,
        ha_device_id="br-online",
        friendly_name="Online Router",
        online=True,
    )
    await _seed_router(
        session,
        ha_device_id="br-offline",
        friendly_name="Offline Router",
        online=False,
    )
    await session.commit()

    rule = ThreadBorderRouterOfflineRule()
    results = await rule.evaluate(_ctx(session))

    assert len(results) == 1
    assert results[0].target_id == offline_device.id
    assert results[0].target_id != online_device.id
    assert "Offline Router" in results[0].message
