"""Frigate detection latency sustained above SLO (feature 017, FR-036/37).

Maintains an in-memory rolling window of per-camera inference latency from
Frigate's ``/api/stats`` payload. When the P95 over the window meets or
exceeds ``frigate_detection_latency_p95_ms`` sustained for at least
``frigate_detection_latency_window_s`` seconds, fires a per-camera alert.

No automatic CPU/Coral failover is performed — per Clarification Q5 in the
017 spec, this rule is observability-only. If it fires repeatedly under
real load, a follow-up feature will add a failover path.

Rolling-window state lives on the rule instance. Like the escalation
counters in ``rule_engine``, this is in-memory only — a process restart
re-arms the window, which is acceptable for a single-admin home lab
(constitution II + existing precedent).
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from app.services.rules.base import Rule, RuleContext, RuleResult


class FrigateDetectionLatencyRule(Rule):
    id = "frigate_detection_latency"
    name = "Frigate detection latency high"
    severity = "warning"
    # The rule engine's own sustained-window filter is bypassed (0) because
    # this rule implements a richer P95-over-window semantic internally.
    sustained_window = timedelta(0)

    def __init__(self) -> None:
        # Per-camera deque of (observed_at, inference_ms). Pruned each
        # evaluate() call to the configured window. Separate rule instance
        # per RULES-list entry, so one deque per camera is fine.
        self._samples: dict[str, deque[tuple[datetime, float]]] = {}

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        if ctx.frigate_stats is None:
            return []

        threshold_ms = ctx.thresholds.get("frigate_detection_latency_p95_ms")
        window_s = ctx.thresholds.get("frigate_detection_latency_window_s")
        if threshold_ms is None or window_s is None:
            return []
        threshold_f = float(threshold_ms)
        window = timedelta(seconds=float(window_s))
        cutoff = ctx.now - window

        results: list[RuleResult] = []
        camera_to_latency = _extract_camera_latencies(ctx.frigate_stats)

        for camera_name, latency_ms in camera_to_latency.items():
            buf = self._samples.setdefault(camera_name, deque())
            buf.append((ctx.now, latency_ms))
            while buf and buf[0][0] < cutoff:
                buf.popleft()

            # Only judge once the window is full enough to be meaningful.
            if not buf:
                continue
            oldest = buf[0][0]
            if ctx.now - oldest < window:
                continue

            p95 = _p95([ms for _, ms in buf])
            if p95 is None or p95 < threshold_f:
                continue

            results.append(
                RuleResult(
                    target_type="system",
                    target_id=_camera_target_id(camera_name),
                    message=(
                        f"Frigate detection latency P95 {p95:.0f} ms on "
                        f"'{camera_name}' (threshold {threshold_f:.0f} ms "
                        f"over {int(window.total_seconds())}s window)"
                    ),
                    rule_id_override=f"frigate_detection_latency:{camera_name}",
                )
            )

        return results


def _extract_camera_latencies(stats: dict) -> dict[str, float]:
    """Extract per-camera inference latency (ms) from an /api/stats payload.

    Frigate's /api/stats exposes a top-level entry per camera with keys
    including ``detection_fps``, ``process_fps``, ``skipped_fps``, and
    (crucially) ``detector`` rolled-up metrics. Different Frigate versions
    surface the inference latency under slightly different keys; we look
    in the most common places and return anything we find.
    """
    out: dict[str, float] = {}
    # Frigate groups camera stats under a top-level "cameras" key in recent
    # versions, and directly at the top level in older ones. Handle both.
    cameras = stats.get("cameras")
    iterable = cameras if isinstance(cameras, dict) else stats

    for camera_name, camera_stats in iterable.items():
        if not isinstance(camera_stats, dict):
            continue
        latency = _first_numeric(
            camera_stats,
            "detection_inference_speed",
            "inference_speed",
            "detection_latency_ms",
        )
        if latency is not None:
            out[camera_name] = float(latency)

    # Fallback: detector-scoped global latency under service.detectors.<name>.
    # Attribute to every camera we know about.
    if not out:
        detectors = (stats.get("service") or {}).get("detectors") or {}
        for _name, det in detectors.items():
            if not isinstance(det, dict):
                continue
            latency = _first_numeric(det, "inference_speed")
            if latency is None:
                continue
            cameras_block = (
                cameras if isinstance(cameras, dict) else stats.get("cameras") or {}
            )
            for camera_name in cameras_block.keys():
                out[camera_name] = float(latency)
    return out


def _first_numeric(d: dict, *keys: str) -> float | None:
    for key in keys:
        v = d.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _p95(samples: list[float]) -> float | None:
    if not samples:
        return None
    if len(samples) == 1:
        return samples[0]
    s = sorted(samples)
    # Nearest-rank P95 — cheap and deterministic.
    idx = max(0, min(len(s) - 1, int(round(0.95 * (len(s) - 1)))))
    return s[idx]


def _camera_target_id(camera_name: str) -> int:
    """Stable 31-bit positive integer target_id derived from the camera name,
    so rule_engine dedup can key per-camera alerts across cycles."""
    # Same pattern as ThreadBorderRouterOfflineRule's synthetic target IDs.
    h = 0
    for ch in camera_name:
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return h
