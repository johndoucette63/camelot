"""VPN leak watchdog — feature 015 US-2.

Probes Deluge's external IP via SSH+docker on every rule-engine cycle.
If the observed IP matches the configured denylist (minimum entry: home
WAN IP), emits a critical alert. After three consecutive leak detections
on the same target, the engine invokes ``on_escalate`` which stops Deluge
and emits a distinct ``vpn_leak:remediation`` alert.

Probe state is also kept in a module-level dict consumed by the
``GET /vpn-status`` endpoint (FR-013) — this is the source of truth for
the dashboard card and top-nav pill.

The probe runs inline within ``evaluate``: SSH subprocess takes ~1-2s on
healthy LAN, well within the 60s rule-engine cycle. If the probe takes
longer than ``vpn_probe_timeout_seconds`` it is treated as a soft warning
(yellow), NOT a leak — see FR-014 + Clarification Q1.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.services.remediation import stop_container
from app.services.rules.base import Rule, RuleContext, RuleResult

logger = logging.getLogger(__name__)

# Module-level probe state — consumed by routers/vpn.py for the dashboard.
# In-memory; resets on Advisor restart, which is the documented tradeoff
# (see 015 spec data-model.md E5 "Escalation counter persistence").
_LATEST_PROBE: dict[str, Any] = {
    "observed_ip": None,
    "status": "unknown",  # "ok" | "leak" | "probe_unreachable" | "unknown"
    "checked_at": None,
    "error": None,
}


def get_latest_probe() -> dict[str, Any]:
    """Read-only accessor used by the /vpn-status endpoint."""
    return dict(_LATEST_PROBE)


# Conservative IP regex — RFC 791 dotted quad, no validation of octet ranges
# (curl will only ever return a real public IP or fail, so no need to be strict).
_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


async def _probe_external_ip() -> tuple[str, str | None, str | None]:
    """Run the external-IP probe via SSH + docker exec.

    Returns ``(status, observed_ip, error)`` where status is one of:
        "ok"                 — probe succeeded, observed_ip is a real IP
        "probe_unreachable"  — probe failed (SSH error, timeout, garbage output)

    Never raises. The caller compares observed_ip against the denylist to
    distinguish "ok" from "leak"; this function only knows whether it
    successfully reached Deluge.
    """
    cmd = [
        "ssh",
        settings.vpn_probe_ssh_target,
        "docker",
        "exec",
        settings.vpn_probe_container_name,
        "curl",
        "-s",
        "--max-time",
        "5",
        "ifconfig.me",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=settings.vpn_probe_timeout_seconds,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return ("probe_unreachable", None, f"probe timed out after {settings.vpn_probe_timeout_seconds}s")
    except (OSError, asyncio.SubprocessError) as exc:
        return ("probe_unreachable", None, f"failed to invoke ssh: {exc}")

    if proc.returncode != 0:
        err = (stderr.decode("utf-8", errors="replace") or "ssh non-zero exit").strip()
        return ("probe_unreachable", None, f"probe exit {proc.returncode}: {err[:200]}")

    observed = stdout.decode("utf-8", errors="replace").strip()
    if not _IP_RE.match(observed):
        return ("probe_unreachable", None, f"unexpected probe output: {observed[:200]!r}")

    return ("ok", observed, None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VpnLeakRule(Rule):
    id = "vpn_leak"
    name = "Deluge VPN leak"
    severity = "critical"
    # Each probe result is independent — we don't want a sustained-window
    # filter on top of "is the IP currently leaking?". Engine's escalation
    # counter handles the "three in a row" semantics.
    sustained_window = timedelta(0)
    escalation_threshold = settings.vpn_leak_escalation_threshold

    # Synthetic single target_id used for all leak alerts. We don't have a
    # ServiceDefinition row for "deluge-vpn" — the rule operates on a
    # logical target. Use a stable sentinel so engine-level dedup works.
    DELUGE_VPN_TARGET_ID = 0

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        denylist = settings.vpn_leak_denylist_ips_set

        status, observed_ip, error = await _probe_external_ip()

        # Update module-level state for the /vpn-status endpoint
        _LATEST_PROBE["observed_ip"] = observed_ip
        _LATEST_PROBE["checked_at"] = _utcnow().isoformat() + "Z"
        _LATEST_PROBE["error"] = error

        if status == "probe_unreachable":
            # FR-014: soft warning, NOT a leak alert. Surface via endpoint
            # state but do not emit a RuleResult (alert).
            _LATEST_PROBE["status"] = "probe_unreachable"
            logger.warning(
                "vpn_leak.probe_unreachable",
                extra={"event": "vpn_leak.probe_unreachable", "error": error},
            )
            return []

        if observed_ip in denylist:
            _LATEST_PROBE["status"] = "leak"
            logger.error(
                "vpn_leak.detected",
                extra={
                    "event": "vpn_leak.detected",
                    "observed_ip": observed_ip,
                    "denylist_size": len(denylist),
                },
            )
            return [
                RuleResult(
                    target_type="service",
                    target_id=self.DELUGE_VPN_TARGET_ID,
                    message=f"Deluge egressing on {observed_ip} (matches denylist)",
                )
            ]

        # Healthy: observed IP is not on the denylist.
        _LATEST_PROBE["status"] = "ok"
        return []

    async def on_escalate(
        self, result: RuleResult, ctx: RuleContext
    ) -> RuleResult | None:
        """Three consecutive leaks → stop the Deluge container.

        Returns a follow-up RuleResult that the engine emits as a distinct
        ``vpn_leak:remediation`` alert (via rule_id_override).
        """
        host = settings.vpn_probe_ssh_target
        container = settings.vpn_probe_container_name

        ok, err = await stop_container(host, container)
        observed_ip = _LATEST_PROBE.get("observed_ip") or "unknown"

        if ok:
            logger.warning(
                "vpn_leak.remediation.fired",
                extra={
                    "event": "vpn_leak.remediation.fired",
                    "host": host,
                    "container": container,
                    "observed_ip": observed_ip,
                },
            )
            message = (
                f"Auto-stopped Deluge after {self.escalation_threshold} consecutive "
                f"leak detections (latest IP: {observed_ip})"
            )
        else:
            logger.error(
                "vpn_leak.remediation.failed",
                extra={
                    "event": "vpn_leak.remediation.failed",
                    "host": host,
                    "container": container,
                    "error": err,
                },
            )
            message = (
                f"Auto-stop attempted after {self.escalation_threshold} consecutive "
                f"leak detections but FAILED: {err} (observed IP: {observed_ip})"
            )

        return RuleResult(
            target_type=result.target_type,
            target_id=result.target_id,
            message=message,
            rule_id_override=f"{self.id}:remediation",
        )
