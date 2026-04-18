"""Thread border router offline rule (feature 016, US-2).

Fires when HA reports a Thread border router as ``online=false``. The
alert prefers to target a merged ``devices`` row (so it shows up on the
Devices page with full provenance), but falls back to a synthetic target
when no inventory row exists — HA's WebSocket-sourced border routers
(HomePods, Aqara hubs, etc.) are identified by their Thread
``extended_address`` which has no relation to HA's device registry id,
so the inventory merge cannot pair them and the rule must still fire.

The rule is stateless — the rule engine's standard dedup on
``(rule_id, target_type, target_id)`` handles "fires once, auto-resolves"
semantics. When the router transitions back to ``online=true`` on a later
cycle the rule emits nothing for it and the engine resolves the alert.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from app.models.device import Device
from app.models.thread_border_router import ThreadBorderRouter
from app.services.rules.base import Rule, RuleContext, RuleResult

logger = logging.getLogger(__name__)


def _synthetic_target_id(ha_device_id: str) -> int:
    """Stable 31-bit positive int derived from the Thread extended_address.

    Kept in range [0, 2**31 - 1] so it fits comfortably in a signed 32-bit
    DB column even on SQLite. Stable across process restarts because HA's
    extended_address is a fixed-length hex string.
    """
    # Try to parse as hex first (``extended_address`` is a 16-char hex
    # string in HA's Thread WS payload). Fall back to Python's hash for
    # non-hex ids.
    try:
        return int(ha_device_id, 16) & 0x7FFFFFFF
    except ValueError:
        return abs(hash(ha_device_id)) & 0x7FFFFFFF


class ThreadBorderRouterOfflineRule(Rule):
    """Critical alert when HA reports a Thread border router offline."""

    id = "thread_border_router_offline"
    name = "Thread border router offline"
    severity = "critical"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        routers = (
            (await ctx.session.execute(select(ThreadBorderRouter)))
            .scalars()
            .all()
        )
        if not routers:
            return []

        results: list[RuleResult] = []
        for router in routers:
            if router.online:
                continue

            device = (
                await ctx.session.execute(
                    select(Device).where(
                        Device.ha_device_id == router.ha_device_id
                    )
                )
            ).scalar_one_or_none()

            if device is not None:
                target_type = "device"
                target_id = device.id
            else:
                # No merged inventory row — expected when the border
                # router was discovered via WebSocket (identified by
                # Thread extended_address, which is not an HA device id).
                # Use a synthetic, stable target id so the alert still
                # dedups correctly across cycles.
                target_type = "ha_device"
                target_id = _synthetic_target_id(router.ha_device_id)

            results.append(
                RuleResult(
                    target_type=target_type,
                    target_id=target_id,
                    message=(
                        f"Thread border router '{router.friendly_name}' is "
                        "offline — Thread devices may have lost connectivity"
                    ),
                )
            )
        return results
