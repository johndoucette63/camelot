"""Persistent unknown device on the LAN.

Fires when the same MAC appears as an "unknown" (not in the curated
inventory) device across ≥3 consecutive recent scans spanning ≥30 minutes.

Since the unknown device is not a row in ``devices``, the dedup target uses
a MAC-suffixed rule_id (``unknown_device:aa:bb:cc:dd:ee:ff``). The engine
passes that override through ``RuleResult.rule_id_override`` so dedup works
per MAC without adding a new target column.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models.device import Device
from app.models.event import Event
from app.services.rules.base import Rule, RuleContext, RuleResult

MIN_CONSECUTIVE_SCANS = 3
MIN_SPAN = timedelta(minutes=30)


class UnknownDeviceRule(Rule):
    id = "unknown_device"
    name = "Unknown device on LAN"
    severity = "warning"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        if len(ctx.recent_scans) < MIN_CONSECUTIVE_SCANS:
            return []

        # Look at the most recent MIN_CONSECUTIVE_SCANS scans; they must
        # span at least MIN_SPAN wall-clock.
        window = ctx.recent_scans[:MIN_CONSECUTIVE_SCANS]
        first_scan = window[-1]
        last_scan = window[0]
        if (
            first_scan.started_at is None
            or last_scan.started_at is None
            or last_scan.started_at - first_scan.started_at < MIN_SPAN
        ):
            return []

        scan_ids = [s.id for s in window]

        # Known MACs from inventory (excluded from alerting).
        known_q = select(Device.mac_address).where(
            Device.is_known_device.is_(True)
        )
        known = {
            m.lower()
            for m in (await ctx.session.execute(known_q)).scalars()
            if m
        }

        # MAC sightings recorded as `device_seen` events per scan.
        events_q = select(Event.scan_id, Device.mac_address).join(
            Device, Event.device_id == Device.id
        ).where(Event.scan_id.in_(scan_ids))
        sightings: dict[str, set[int]] = {}
        for scan_id, mac in (await ctx.session.execute(events_q)).all():
            if not mac:
                continue
            mac_l = mac.lower()
            if mac_l in known:
                continue
            sightings.setdefault(mac_l, set()).add(scan_id)

        results: list[RuleResult] = []
        for mac, scans_with_mac in sightings.items():
            if len(scans_with_mac) < MIN_CONSECUTIVE_SCANS:
                continue
            results.append(
                RuleResult(
                    target_type="system",
                    target_id=None,
                    message=f"Unknown device {mac} seen on LAN",
                    rule_id_override=f"{self.id}:{mac}",
                )
            )
        return results
