"""Tests for the Frigate detection-latency rule (feature 017, FR-036/37)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.rules.base import RuleContext
from app.services.rules.frigate_detection_latency import (
    FrigateDetectionLatencyRule,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ctx(
    *,
    stats: dict | None,
    now: datetime,
    threshold_ms: float | None = 2000.0,
    window_s: float | None = 300.0,
) -> RuleContext:
    thresholds: dict[str, Decimal] = {}
    if threshold_ms is not None:
        thresholds["frigate_detection_latency_p95_ms"] = Decimal(str(threshold_ms))
    if window_s is not None:
        thresholds["frigate_detection_latency_window_s"] = Decimal(str(window_s))
    return RuleContext(
        now=now, session=None, thresholds=thresholds, frigate_stats=stats
    )


def _stats(cameras: dict[str, float]) -> dict:
    """Modern Frigate /api/stats shape with per-camera inference_speed."""
    return {
        "cameras": {
            name: {
                "detection_fps": 5.0,
                "inference_speed": ms,
            }
            for name, ms in cameras.items()
        }
    }


@pytest.mark.asyncio
async def test_fires_when_window_full_and_p95_breaches():
    rule = FrigateDetectionLatencyRule()
    start = _utcnow()
    # Feed 7 minutes of samples (window is 5 minutes, so the last 5 minutes
    # are what we judge). All samples well above threshold.
    for i in range(42):  # 42 * 10s = 420s = 7 minutes
        now = start + timedelta(seconds=i * 10)
        results = await rule.evaluate(
            _ctx(
                stats=_stats({"doorbell": 3000.0}),
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    # The last cycle's results are what we care about.
    assert len(results) == 1
    r = results[0]
    assert r.target_type == "system"
    assert r.rule_id_override == "frigate_detection_latency:doorbell"
    assert "3000" in r.message or "3,000" in r.message  # P95 value
    assert "doorbell" in r.message


@pytest.mark.asyncio
async def test_silent_before_window_is_full():
    """First few minutes of samples must not fire — window not populated."""
    rule = FrigateDetectionLatencyRule()
    start = _utcnow()
    # Feed 2 minutes of samples — well below the 5-minute window.
    final_results = None
    for i in range(12):  # 12 * 10s = 120s
        now = start + timedelta(seconds=i * 10)
        final_results = await rule.evaluate(
            _ctx(
                stats=_stats({"doorbell": 5000.0}),  # blatantly high
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    assert final_results == []


@pytest.mark.asyncio
async def test_silent_when_p95_under_threshold():
    rule = FrigateDetectionLatencyRule()
    start = _utcnow()
    final_results = None
    for i in range(42):
        now = start + timedelta(seconds=i * 10)
        final_results = await rule.evaluate(
            _ctx(
                stats=_stats({"doorbell": 500.0}),  # well under 2000
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    assert final_results == []


@pytest.mark.asyncio
async def test_recovery_clears_fire():
    """After a sustained breach, latency drops back — rule stops firing."""
    rule = FrigateDetectionLatencyRule()
    start = _utcnow()

    # 7 minutes high -> should fire on the last one.
    for i in range(42):
        now = start + timedelta(seconds=i * 10)
        breach_results = await rule.evaluate(
            _ctx(
                stats=_stats({"doorbell": 3000.0}),
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    assert len(breach_results) == 1

    # Another 7 minutes of low latency — deque slides forward; recovery.
    for i in range(42, 84):
        now = start + timedelta(seconds=i * 10)
        recovery_results = await rule.evaluate(
            _ctx(
                stats=_stats({"doorbell": 300.0}),
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    assert recovery_results == []


@pytest.mark.asyncio
async def test_noop_when_frigate_stats_missing():
    rule = FrigateDetectionLatencyRule()
    results = await rule.evaluate(
        _ctx(stats=None, now=_utcnow(), threshold_ms=2000.0, window_s=300.0)
    )
    assert results == []


@pytest.mark.asyncio
async def test_noop_when_thresholds_missing():
    rule = FrigateDetectionLatencyRule()
    start = _utcnow()
    for i in range(42):
        now = start + timedelta(seconds=i * 10)
        results = await rule.evaluate(
            _ctx(
                stats=_stats({"doorbell": 5000.0}),
                now=now,
                threshold_ms=None,
                window_s=None,
            )
        )
    assert results == []


@pytest.mark.asyncio
async def test_multiple_cameras_each_judged_independently():
    """One camera breaches, the other doesn't — fire once, for the breach."""
    rule = FrigateDetectionLatencyRule()
    start = _utcnow()
    final_results = None
    for i in range(42):
        now = start + timedelta(seconds=i * 10)
        final_results = await rule.evaluate(
            _ctx(
                stats=_stats({"doorbell": 3000.0, "garage": 400.0}),
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    assert len(final_results) == 1
    assert final_results[0].rule_id_override == "frigate_detection_latency:doorbell"


@pytest.mark.asyncio
async def test_per_camera_target_id_is_stable():
    """Same camera name => same target_id across cycles (dedup precondition)."""
    rule_a = FrigateDetectionLatencyRule()
    rule_b = FrigateDetectionLatencyRule()
    start = _utcnow()
    last_a = None
    last_b = None
    for i in range(42):
        now = start + timedelta(seconds=i * 10)
        last_a = await rule_a.evaluate(
            _ctx(
                stats=_stats({"doorbell": 3000.0}),
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
        last_b = await rule_b.evaluate(
            _ctx(
                stats=_stats({"doorbell": 3000.0}),
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    assert len(last_a) == 1 and len(last_b) == 1
    assert last_a[0].target_id == last_b[0].target_id
    assert last_a[0].target_id > 0  # 31-bit positive


@pytest.mark.asyncio
async def test_legacy_stats_shape_with_cameras_at_top_level():
    """Older Frigate versions put cameras at the top level of /api/stats."""
    rule = FrigateDetectionLatencyRule()
    start = _utcnow()
    final = None
    for i in range(42):
        now = start + timedelta(seconds=i * 10)
        legacy_stats = {
            "doorbell": {"detection_fps": 5.0, "inference_speed": 3000.0},
            "service": {"uptime": 1234},  # non-camera key; must be ignored
        }
        final = await rule.evaluate(
            _ctx(
                stats=legacy_stats,
                now=now,
                threshold_ms=2000.0,
                window_s=300.0,
            )
        )
    assert len(final) == 1
    assert "doorbell" in final[0].message
