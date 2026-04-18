"""Home Assistant connection-health rules (feature 016, FR-023/FR-024).

Reads the singleton ``home_assistant_connections`` row and emits at most
one ``RuleResult`` per cycle based on the current error class:

* ``auth_failure``       -> critical  ("rotate the token")
* ``unreachable``        -> warning   ("snapshot may be stale")
* ``unexpected_payload`` -> warning   ("check the base URL")
* any other state        -> no alert (auto-resolves any existing one via
  the rule-engine's standard auto-resolve flow in 011 semantics)

When ``base_url IS NULL`` the connection is "not configured" which is not
an error — the rules are no-ops and any prior alert auto-resolves.

The three error classes are split into three ``Rule`` subclasses so each
gets its own severity (the base ``Rule`` contract carries one severity
per rule) and its own dedup / auto-resolve channel.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models.home_assistant_connection import HomeAssistantConnection
from app.services.rules.base import Rule, RuleContext, RuleResult

_HA_CONNECTION_TARGET_ID = 1  # singleton row id=1


async def _fetch_connection(ctx: RuleContext) -> HomeAssistantConnection | None:
    return (
        await ctx.session.execute(
            select(HomeAssistantConnection).where(
                HomeAssistantConnection.id == _HA_CONNECTION_TARGET_ID
            )
        )
    ).scalar_one_or_none()


def _result(message: str) -> RuleResult:
    return RuleResult(
        target_type="ha_connection",
        target_id=_HA_CONNECTION_TARGET_ID,
        message=message,
    )


class HaConnectionAuthFailureRule(Rule):
    """FR-024 — critical when the stored token is rejected."""

    id = "ha_connection_health:auth_failure"
    name = "Home Assistant authentication failed"
    severity = "critical"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        row = await _fetch_connection(ctx)
        if row is None or row.base_url is None:
            return []
        if row.last_error != "auth_failure":
            return []
        return [
            _result(
                "Home Assistant authentication failed — rotate the token "
                "in Settings → Home Assistant"
            )
        ]


class HaConnectionUnreachableRule(Rule):
    """FR-023 — warning when HA cannot be reached (network / timeout / 5xx)."""

    id = "ha_connection_health:unreachable"
    name = "Home Assistant unreachable"
    severity = "warning"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        row = await _fetch_connection(ctx)
        if row is None or row.base_url is None:
            return []
        if row.last_error != "unreachable":
            return []
        return [
            _result(
                "Home Assistant is unreachable — snapshot may be stale"
            )
        ]


class HaConnectionUnexpectedPayloadRule(Rule):
    """Warning when HA returned a non-JSON / unexpected 2xx body."""

    id = "ha_connection_health:unexpected_payload"
    name = "Home Assistant unexpected response"
    severity = "warning"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        row = await _fetch_connection(ctx)
        if row is None or row.base_url is None:
            return []
        if row.last_error != "unexpected_payload":
            return []
        return [
            _result(
                "Home Assistant returned an unexpected response — check "
                "the base URL"
            )
        ]
