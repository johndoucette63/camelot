"""Sustained high CPU on a Pi device."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.services.rules.base import Rule, RuleContext, RuleResult


def _is_pi(device) -> bool:
    vendor = (device.vendor or "").lower()
    return "raspberry" in vendor


class PiCpuHighRule(Rule):
    id = "pi_cpu_high"
    name = "Sustained high CPU on Pi"
    severity = "warning"
    sustained_window = timedelta(minutes=5)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        threshold = ctx.thresholds.get("cpu_percent")
        if threshold is None:
            return []
        threshold_f = float(threshold)

        results: list[RuleResult] = []
        for device in ctx.devices:
            if not _is_pi(device):
                continue
            metrics = ctx.device_metrics.get(device.id)
            if not metrics:
                continue
            cpu = metrics.get("cpu_percent")
            if cpu is None:
                continue
            if cpu >= threshold_f:
                label = device.hostname or device.ip_address
                results.append(
                    RuleResult(
                        target_type="device",
                        target_id=device.id,
                        message=(
                            f"{label} CPU at {cpu:.0f}% "
                            f"(threshold {threshold_f:.0f}%) — "
                            "consider migrating heavy services to HOLYGRAIL"
                        ),
                    )
                )
        return results
