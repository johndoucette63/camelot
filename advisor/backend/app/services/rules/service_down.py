"""Service has been down (status='red') for at least the configured threshold."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models.health_check_result import HealthCheckResult
from app.services.rules.base import Rule, RuleContext, RuleResult


class ServiceDownRule(Rule):
    id = "service_down"
    name = "Service down"
    severity = "critical"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        minutes = ctx.thresholds.get("service_down_minutes")
        if minutes is None:
            return []
        window = timedelta(minutes=float(minutes))
        cutoff = ctx.now - window

        results: list[RuleResult] = []
        for service in ctx.services:
            latest = ctx.health_results.get(service.id)
            if latest is None or latest.status != "red":
                continue

            # Look for the most recent non-red result; if it's older than
            # the cutoff (or there isn't one), the service has been red
            # for at least `minutes`.
            q = (
                select(HealthCheckResult.checked_at)
                .where(
                    HealthCheckResult.service_id == service.id,
                    HealthCheckResult.status != "red",
                )
                .order_by(HealthCheckResult.checked_at.desc())
                .limit(1)
            )
            last_healthy = (await ctx.session.execute(q)).scalar_one_or_none()

            if last_healthy is not None and last_healthy > cutoff:
                continue

            label = f"{service.name} on {service.host_label}"
            results.append(
                RuleResult(
                    target_type="service",
                    target_id=service.id,
                    message=(
                        f"{label} has been down for ≥ {int(float(minutes))} minutes"
                    ),
                )
            )
        return results
