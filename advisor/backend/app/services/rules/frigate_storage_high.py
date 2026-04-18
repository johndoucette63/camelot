"""Frigate footage volume filling toward overflow (feature 017, FR-034/35).

Fires when the reported fill percent of Frigate's recordings volume
(``/mnt/frigate`` on HOLYGRAIL, surfaced to Frigate as ``/media/frigate``)
meets or exceeds the ``frigate_storage_fill_percent`` threshold. The point
is to alert BEFORE retention caps are bypassed by raw disk overflow.

Data source: ``ctx.frigate_stats`` populated each cycle by
``rule_engine._probe_frigate_stats``. No data this cycle = no-op; we
degrade gracefully if Frigate is down (constitution V — silent failures
are unacceptable, but emitting a separate, more diagnostic alert when
Frigate itself is unreachable is the existing pattern's job via service
health checks, not this rule's).
"""
from __future__ import annotations

from datetime import timedelta

from app.services.rules.base import Rule, RuleContext, RuleResult


class FrigateStorageHighRule(Rule):
    id = "frigate_storage_high"
    name = "Frigate footage volume filling"
    severity = "warning"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        if ctx.frigate_stats is None:
            return []

        threshold = ctx.thresholds.get("frigate_storage_fill_percent")
        if threshold is None:
            return []
        threshold_f = float(threshold)

        fill = _extract_fill_percent(ctx.frigate_stats)
        if fill is None:
            return []

        if fill < threshold_f:
            return []

        return [
            RuleResult(
                target_type="system",
                target_id=None,
                message=(
                    f"Frigate footage volume at {fill:.0f}% "
                    f"(threshold {threshold_f:.0f}% — retention caps may be "
                    "bypassed by overflow if not addressed)"
                ),
            )
        ]


def _extract_fill_percent(stats: dict) -> float | None:
    """Locate the Frigate recordings volume fill percent in an /api/stats payload.

    Frigate exposes disk metrics under ``service.storage``, keyed by the
    container mount path. The recordings volume is ``/media/frigate``. The
    dict values include ``used``, ``total``, and ``mount_type``. We compute
    fill percent from used/total for forward-compat with schema shifts.
    """
    service = stats.get("service") or {}
    storage = service.get("storage") or {}
    entry = storage.get("/media/frigate")
    if not isinstance(entry, dict):
        return None

    used = entry.get("used")
    total = entry.get("total")
    if not isinstance(used, (int, float)) or not isinstance(total, (int, float)):
        return None
    if total <= 0:
        return None

    return (float(used) / float(total)) * 100.0
