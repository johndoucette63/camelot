"""Tests for the HA-connection-health rules (feature 016, T037a).

The rule module exposes three subclasses — one per error class — so each
gets its own severity + dedup channel. Each rule reads the singleton
``home_assistant_connections`` row and emits 0..1 ``RuleResult`` based on
the current ``last_error`` classification.

| last_error            | Rule                                | Severity  | Message must mention |
|-----------------------|-------------------------------------|-----------|----------------------|
| None                  | — (all rules no-op)                 | —         | — |
| auth_failure          | HaConnectionAuthFailureRule         | critical  | "authentication failed" |
| unreachable           | HaConnectionUnreachableRule         | warning   | "unreachable" |
| unexpected_payload    | HaConnectionUnexpectedPayloadRule   | warning   | "unexpected" |

When ``base_url IS NULL`` (unconfigured), every rule is a no-op regardless
of ``last_error``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.home_assistant_connection import HomeAssistantConnection
from app.security import encrypt_token
from app.services.rules.base import RuleContext
from app.services.rules.ha_connection_health import (
    HaConnectionAuthFailureRule,
    HaConnectionUnexpectedPayloadRule,
    HaConnectionUnreachableRule,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _utcnow():
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


async def _seed_connection(
    session,
    *,
    configured: bool = True,
    last_error: str | None = None,
) -> None:
    conn = HomeAssistantConnection(id=1)
    if configured:
        conn.base_url = "http://homeassistant.local:8123"
        conn.token_ciphertext = encrypt_token("llat_x")
        conn.last_success_at = _utcnow()
    if last_error:
        conn.last_error = last_error
        conn.last_error_at = _utcnow()
    session.add(conn)
    await session.commit()


# ── (a) last_error = None → every rule is a no-op ──────────────────────


@pytest.mark.asyncio
async def test_no_error_all_rules_noop(rule_env):
    session = rule_env
    await _seed_connection(session, configured=True, last_error=None)

    for rule_cls in (
        HaConnectionAuthFailureRule,
        HaConnectionUnreachableRule,
        HaConnectionUnexpectedPayloadRule,
    ):
        results = await rule_cls().evaluate(_ctx(session))
        assert results == [], f"{rule_cls.__name__} must not fire when last_error is None"


# ── (b) auth_failure → HaConnectionAuthFailureRule only, critical ──────


@pytest.mark.asyncio
async def test_auth_failure_fires_critical_rule(rule_env):
    session = rule_env
    await _seed_connection(session, last_error="auth_failure")

    auth_results = await HaConnectionAuthFailureRule().evaluate(_ctx(session))
    assert len(auth_results) == 1
    assert "authentication failed" in auth_results[0].message.lower()
    assert auth_results[0].target_type == "ha_connection"
    assert auth_results[0].target_id == 1
    assert HaConnectionAuthFailureRule.severity == "critical"

    # Other two rules must not fire for this classification.
    for rule_cls in (HaConnectionUnreachableRule, HaConnectionUnexpectedPayloadRule):
        assert await rule_cls().evaluate(_ctx(session)) == []


# ── (c) unreachable → HaConnectionUnreachableRule only, warning ────────


@pytest.mark.asyncio
async def test_unreachable_fires_warning_rule(rule_env):
    session = rule_env
    await _seed_connection(session, last_error="unreachable")

    results = await HaConnectionUnreachableRule().evaluate(_ctx(session))
    assert len(results) == 1
    assert "unreachable" in results[0].message.lower()
    assert results[0].target_type == "ha_connection"
    assert HaConnectionUnreachableRule.severity == "warning"

    for rule_cls in (HaConnectionAuthFailureRule, HaConnectionUnexpectedPayloadRule):
        assert await rule_cls().evaluate(_ctx(session)) == []


# ── (d) unexpected_payload → HaConnectionUnexpectedPayloadRule only ────


@pytest.mark.asyncio
async def test_unexpected_payload_fires_warning_rule(rule_env):
    session = rule_env
    await _seed_connection(session, last_error="unexpected_payload")

    results = await HaConnectionUnexpectedPayloadRule().evaluate(_ctx(session))
    assert len(results) == 1
    assert "unexpected" in results[0].message.lower()
    assert HaConnectionUnexpectedPayloadRule.severity == "warning"

    for rule_cls in (HaConnectionAuthFailureRule, HaConnectionUnreachableRule):
        assert await rule_cls().evaluate(_ctx(session)) == []


# ── (e) unconfigured connection → every rule no-ops regardless ─────────


@pytest.mark.asyncio
async def test_unconfigured_all_rules_noop(rule_env):
    session = rule_env
    # base_url is NULL but last_error is set — every rule must still no-op.
    await _seed_connection(session, configured=False, last_error="auth_failure")

    for rule_cls in (
        HaConnectionAuthFailureRule,
        HaConnectionUnreachableRule,
        HaConnectionUnexpectedPayloadRule,
    ):
        results = await rule_cls().evaluate(_ctx(session))
        assert results == [], (
            f"{rule_cls.__name__} must no-op when base_url is NULL even if last_error is set"
        )


# ── (f) stateless: two consecutive calls emit identical results ────────


@pytest.mark.asyncio
async def test_rule_is_stateless_across_cycles(rule_env):
    session = rule_env
    await _seed_connection(session, last_error="auth_failure")

    rule = HaConnectionAuthFailureRule()
    first = await rule.evaluate(_ctx(session))
    second = await rule.evaluate(_ctx(session))

    assert len(first) == 1
    assert len(second) == 1
    # Dedup belongs to the rule-engine, not the rule — emit the same result.
    assert first[0].message == second[0].message
    assert first[0].target_type == second[0].target_type
    assert first[0].target_id == second[0].target_id
