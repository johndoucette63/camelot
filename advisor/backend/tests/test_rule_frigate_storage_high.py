"""Tests for the Frigate storage-high rule (feature 017, FR-034/35)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services.rules.base import RuleContext
from app.services.rules.frigate_storage_high import FrigateStorageHighRule


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ctx(
    *, stats: dict | None, threshold: float | None = 85.0
) -> RuleContext:
    thresholds: dict[str, Decimal] = {}
    if threshold is not None:
        thresholds["frigate_storage_fill_percent"] = Decimal(str(threshold))
    return RuleContext(
        now=_utcnow(),
        session=None,  # rule doesn't touch the DB
        thresholds=thresholds,
        frigate_stats=stats,
    )


def _stats(used: int, total: int) -> dict:
    return {
        "service": {
            "storage": {
                "/media/frigate": {
                    "used": used,
                    "total": total,
                    "mount_type": "ext4",
                },
                "/tmp/cache": {  # another mount — must be ignored
                    "used": 10,
                    "total": 1000,
                    "mount_type": "tmpfs",
                },
            }
        }
    }


@pytest.mark.asyncio
async def test_fires_when_fill_crosses_threshold():
    rule = FrigateStorageHighRule()
    results = await rule.evaluate(
        _ctx(stats=_stats(used=870, total=1000), threshold=85.0)
    )
    assert len(results) == 1
    r = results[0]
    assert r.target_type == "system"
    assert r.target_id is None
    assert "87%" in r.message
    assert "85%" in r.message


@pytest.mark.asyncio
async def test_silent_below_threshold():
    rule = FrigateStorageHighRule()
    results = await rule.evaluate(
        _ctx(stats=_stats(used=800, total=1000), threshold=85.0)
    )
    assert results == []


@pytest.mark.asyncio
async def test_noop_when_frigate_stats_missing():
    """Frigate probe failed this cycle — rule must degrade silently."""
    rule = FrigateStorageHighRule()
    results = await rule.evaluate(_ctx(stats=None, threshold=85.0))
    assert results == []


@pytest.mark.asyncio
async def test_noop_when_threshold_unset():
    """Migration 009 did not run yet / threshold row missing — no crash."""
    rule = FrigateStorageHighRule()
    results = await rule.evaluate(
        _ctx(stats=_stats(used=990, total=1000), threshold=None)
    )
    assert results == []


@pytest.mark.asyncio
async def test_noop_when_mount_entry_missing():
    """Frigate responded but /media/frigate is absent from storage dict."""
    rule = FrigateStorageHighRule()
    stats = {"service": {"storage": {}}}
    results = await rule.evaluate(_ctx(stats=stats, threshold=85.0))
    assert results == []


@pytest.mark.asyncio
async def test_noop_when_used_or_total_non_numeric():
    rule = FrigateStorageHighRule()
    stats = {
        "service": {
            "storage": {"/media/frigate": {"used": "?", "total": 1000}}
        }
    }
    results = await rule.evaluate(_ctx(stats=stats, threshold=85.0))
    assert results == []


@pytest.mark.asyncio
async def test_noop_when_total_is_zero():
    rule = FrigateStorageHighRule()
    stats = {
        "service": {"storage": {"/media/frigate": {"used": 10, "total": 0}}}
    }
    results = await rule.evaluate(_ctx(stats=stats, threshold=85.0))
    assert results == []


@pytest.mark.asyncio
async def test_resolve_edge_at_exact_threshold():
    """Fires when fill == threshold (>= semantics)."""
    rule = FrigateStorageHighRule()
    results = await rule.evaluate(
        _ctx(stats=_stats(used=850, total=1000), threshold=85.0)
    )
    assert len(results) == 1
