"""Rule-engine mute suppression test (User Story 2).

Covers the integration between ``_is_muted`` and ``run_cycle``: when a
RuleMute row matches a rule result, the alert is still inserted (for
audit) but with ``suppressed=True``, ``alerts_suppressed`` is incremented
instead of ``alerts_created``, and the row is not returned as an active
open alert.

Kept in its own file to avoid touching the existing ``test_rule_engine.py``
suite.
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
from app.models.rule_mute import RuleMute
from app.services import rule_engine
from app.services.rule_engine import _STREAKS, run_cycle
from app.services.rules.base import Rule, RuleContext, RuleResult

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StubRule(Rule):
    id = "stub_rule_mute"
    name = "Stub rule for mute test"
    severity = "warning"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        return [
            RuleResult(
                target_type="device",
                target_id=1,
                message="stub",
            )
        ]


@pytest_asyncio.fixture
async def engine_env(monkeypatch):
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

    monkeypatch.setattr(rule_engine, "RULES", [StubRule()])
    monkeypatch.setattr(rule_engine, "async_session", session_factory)
    monkeypatch.setattr(rule_engine, "_probe_ollama", AsyncMock(return_value=True))

    _STREAKS.clear()

    app = SimpleNamespace(state=SimpleNamespace(container_state={}))

    yield session_factory, app

    _STREAKS.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_mute_suppression(engine_env):
    session_factory, app = engine_env

    # Insert a matching RuleMute row for (stub_rule_mute, 'device', 1).
    now = _now()
    async with session_factory() as session:
        mute = RuleMute(
            rule_id="stub_rule_mute",
            target_type="device",
            target_id=1,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            note="mute for test",
        )
        session.add(mute)
        await session.commit()

    stats = await run_cycle(app)

    # (ii) alerts_suppressed incremented
    assert stats["alerts_suppressed"] == 1
    # (iii) alerts_created stays zero
    assert stats["alerts_created"] == 0

    # (i) exactly one Alert row exists with suppressed=True
    async with session_factory() as session:
        alerts = (await session.execute(select(Alert))).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].suppressed is True
    assert alerts[0].rule_id == "stub_rule_mute"
    assert alerts[0].target_type == "device"
    assert alerts[0].target_id == 1
    assert alerts[0].state == "active"

    # (iv) no non-suppressed open alerts
    async with session_factory() as session:
        open_non_suppressed = (
            await session.execute(
                select(Alert).where(
                    Alert.state == "active",
                    Alert.suppressed.is_(False),
                )
            )
        ).scalars().all()
    assert open_non_suppressed == []
