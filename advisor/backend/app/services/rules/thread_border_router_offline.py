"""Thread border router offline rule (feature 016, US-2).

Fires when a border router HA reports as ``online=false`` has a matching
row in the unified ``devices`` table (joined via ``ha_device_id``).

The rule is stateless — the rule engine's standard dedup on
``(rule_id, target_id)`` handles "fires once, auto-resolves" semantics.
When the border router transitions back to ``online=true`` on a later
cycle, the rule emits nothing for it and the engine resolves the alert.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from app.models.device import Device
from app.models.thread_border_router import ThreadBorderRouter
from app.services.rules.base import Rule, RuleContext, RuleResult

logger = logging.getLogger(__name__)


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
            if device is None:
                # No merged inventory row — we cannot target the alert at a
                # Device.id. Skip and let the inventory-merge pass pick it
                # up on a later cycle.
                logger.warning(
                    "Thread border router %s has no merged inventory row — skipping",
                    router.ha_device_id,
                )
                continue

            results.append(
                RuleResult(
                    target_type="device",
                    target_id=device.id,
                    message=(
                        f"Thread border router '{router.friendly_name}' is "
                        "offline — Thread devices may have lost connectivity"
                    ),
                )
            )
        return results
