"""Device has reported no metrics / heartbeats for ≥ threshold minutes."""
from __future__ import annotations

from datetime import timedelta

from app.services.rules.base import Rule, RuleContext, RuleResult


def _has_random_mac(mac: str) -> bool:
    """Return True if the MAC uses the locally-administered bit.

    Apple (and some other) devices rotate their MAC address for privacy.
    The locally-administered bit is the second-least-significant bit of
    the first octet — equivalently, the second hex character of the MAC
    is one of {2,3,6,7,A,B,E,F}.  These devices create ghost records
    each time the MAC rotates, so offline alerts for them are always
    false positives.
    """
    if not mac or len(mac) < 2:
        return False
    return mac[1].upper() in "2367ABEF"


class DeviceOfflineRule(Rule):
    id = "device_offline"
    name = "Device offline"
    severity = "warning"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        minutes = ctx.thresholds.get("device_offline_minutes")
        if minutes is None:
            return []
        window = timedelta(minutes=float(minutes))
        cutoff = ctx.now - window

        results: list[RuleResult] = []
        for device in ctx.devices:
            # Never-seen devices are skipped to avoid false positives on the
            # first scan after deploy. A device is "seen" if it has a
            # last_seen timestamp.
            if device.last_seen is None or device.first_seen is None:
                continue

            # Skip devices with locally-administered (randomized) MACs.
            # Apple devices rotate MACs for privacy, creating ghost records
            # that will always appear offline once the MAC rotates.
            if _has_random_mac(device.mac_address):
                continue

            # Skip devices where offline monitoring is disabled via the UI.
            if not device.monitor_offline:
                continue

            # Authoritative offline check: trust the scanner's is_online flag.
            # The threshold acts as a grace period — only alert once the
            # device has been continuously offline for ≥ threshold minutes,
            # measured from when the scanner last saw it. This avoids false
            # positives for devices whose last_seen is stale only because
            # the scan interval is longer than the threshold.
            if device.is_online:
                continue

            last_seen = device.last_seen
            if last_seen.tzinfo is not None:
                last_seen = last_seen.replace(tzinfo=None)

            if last_seen >= cutoff:
                continue

            label = device.hostname or device.ip_address
            gap_minutes = int((ctx.now - last_seen).total_seconds() / 60)
            results.append(
                RuleResult(
                    target_type="device",
                    target_id=device.id,
                    message=f"{label} has been offline for {gap_minutes} minutes",
                )
            )
        return results
