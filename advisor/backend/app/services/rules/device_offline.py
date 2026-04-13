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

        # When DHCP reassigns an IP or hardware changes, multiple device rows
        # can share the same IP.  Only alert for the most-recently-seen device
        # per IP so the same address doesn't appear twice in the alert list.
        best_by_ip: dict[str, tuple] = {}

        candidates = []
        for device in ctx.devices:
            if device.last_seen is None or device.first_seen is None:
                continue
            if _has_random_mac(device.mac_address):
                continue
            if not device.monitor_offline:
                continue
            if device.is_online:
                continue

            last_seen = device.last_seen
            if last_seen.tzinfo is not None:
                last_seen = last_seen.replace(tzinfo=None)

            if last_seen >= cutoff:
                continue

            ip = device.ip_address
            prev = best_by_ip.get(ip)
            if prev is None or last_seen > prev[1]:
                best_by_ip[ip] = (device, last_seen)

        results: list[RuleResult] = []
        for device, last_seen in best_by_ip.values():
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
