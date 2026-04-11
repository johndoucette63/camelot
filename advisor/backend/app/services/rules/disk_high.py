"""Disk usage exceeds threshold on a device."""
from __future__ import annotations

from datetime import timedelta

from app.services.rules.base import Rule, RuleContext, RuleResult


class DiskHighRule(Rule):
    id = "disk_high"
    name = "Disk usage high"
    severity = "warning"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        threshold = ctx.thresholds.get("disk_percent")
        if threshold is None:
            return []
        threshold_f = float(threshold)

        results: list[RuleResult] = []
        for device in ctx.devices:
            metrics = ctx.device_metrics.get(device.id)
            if not metrics:
                continue
            disk = metrics.get("disk_percent")
            if disk is None:
                continue
            if disk >= threshold_f:
                label = device.hostname or device.ip_address
                results.append(
                    RuleResult(
                        target_type="device",
                        target_id=device.id,
                        message=(
                            f"{label} disk at {disk:.0f}% "
                            f"(threshold {threshold_f:.0f}%)"
                        ),
                    )
                )
        return results
