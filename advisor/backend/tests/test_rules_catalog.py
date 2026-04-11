"""Unit tests for each shipped rule in app.services.rules.

Each rule is tested in both "breaching" and "not breaching" branches using
synthetic RuleContext objects built in memory. Rules that query the DB
(service_down, unknown_device) use the shared `db` fixture from conftest.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.device import Device
from app.models.event import Event
from app.models.health_check_result import HealthCheckResult
from app.models.scan import Scan
from app.models.service_definition import ServiceDefinition
from app.services.rules.base import RuleContext
from app.services.rules.device_offline import DeviceOfflineRule
from app.services.rules.disk_high import DiskHighRule
from app.services.rules.ollama_unavailable import OllamaUnavailableRule
from app.services.rules.pi_cpu_high import PiCpuHighRule
from app.services.rules.service_down import ServiceDownRule
from app.services.rules.unknown_device import UnknownDeviceRule


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _device(
    *,
    id: int = 1,
    mac: str = "aa:bb:cc:00:00:01",
    ip: str = "192.168.10.10",
    hostname: str | None = "pi-test",
    vendor: str | None = "Raspberry Pi Trading Ltd",
    last_seen: datetime | None = None,
    first_seen: datetime | None = None,
    is_online: bool = True,
) -> Device:
    now = _now()
    d = Device(
        mac_address=mac,
        ip_address=ip,
        hostname=hostname,
        vendor=vendor,
        first_seen=first_seen if first_seen is not None else now,
        last_seen=last_seen if last_seen is not None else now,
        is_online=is_online,
        consecutive_missed_scans=0,
        is_known_device=False,
    )
    d.id = id
    return d


def _ctx(
    *,
    session=None,
    devices=None,
    services=None,
    health_results=None,
    thresholds=None,
    ollama_healthy=True,
    recent_scans=None,
    device_metrics=None,
    now=None,
) -> RuleContext:
    return RuleContext(
        now=now or _now(),
        session=session if session is not None else MagicMock(),
        devices=devices or [],
        services=services or [],
        health_results=health_results or {},
        thresholds=thresholds or {},
        ollama_healthy=ollama_healthy,
        recent_scans=recent_scans or [],
        device_metrics=device_metrics or {},
    )


# ── PiCpuHighRule ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pi_cpu_high_breaching_fires():
    device = _device(id=1, vendor="Raspberry Pi Trading Ltd")
    ctx = _ctx(
        devices=[device],
        thresholds={"cpu_percent": Decimal("85")},
        device_metrics={1: {"cpu_percent": 92.3}},
    )
    results = await PiCpuHighRule().evaluate(ctx)
    assert len(results) == 1
    r = results[0]
    assert r.target_type == "device"
    assert r.target_id == 1
    assert "92%" in r.message
    assert "85%" in r.message


@pytest.mark.asyncio
async def test_pi_cpu_high_not_breaching_silent():
    device = _device(id=1, vendor="Raspberry Pi Trading Ltd")
    ctx = _ctx(
        devices=[device],
        thresholds={"cpu_percent": Decimal("85")},
        device_metrics={1: {"cpu_percent": 50.0}},
    )
    assert await PiCpuHighRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_pi_cpu_high_non_pi_skipped():
    # Vendor does NOT contain "raspberry" — rule must skip even if over threshold.
    device = _device(id=1, vendor="Intel Corporate")
    ctx = _ctx(
        devices=[device],
        thresholds={"cpu_percent": Decimal("85")},
        device_metrics={1: {"cpu_percent": 99.0}},
    )
    assert await PiCpuHighRule().evaluate(ctx) == []


# ── DiskHighRule ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disk_high_breaching_fires():
    device = _device(id=2, hostname="nas")
    ctx = _ctx(
        devices=[device],
        thresholds={"disk_percent": Decimal("90")},
        device_metrics={2: {"disk_percent": 97.5}},
    )
    results = await DiskHighRule().evaluate(ctx)
    assert len(results) == 1
    assert results[0].target_id == 2
    assert "98%" in results[0].message  # rounded from 97.5 via :.0f


@pytest.mark.asyncio
async def test_disk_high_not_breaching_silent():
    device = _device(id=2, hostname="nas")
    ctx = _ctx(
        devices=[device],
        thresholds={"disk_percent": Decimal("90")},
        device_metrics={2: {"disk_percent": 40.0}},
    )
    assert await DiskHighRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_disk_high_no_metrics_silent():
    # No device_metrics entry — rule must degrade gracefully.
    device = _device(id=3)
    ctx = _ctx(
        devices=[device],
        thresholds={"disk_percent": Decimal("90")},
        device_metrics={},
    )
    assert await DiskHighRule().evaluate(ctx) == []


# ── ServiceDownRule ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_down_breaching_fires(db):
    """Latest result is red AND most-recent-non-red is older than the
    window, so the service has been down the full window.

    Judgment call: the rule treats the window-start as "time since the
    last non-red result", not "time since the latest red". A fresh red
    with no prior non-red history fires on the first cycle.
    """
    now = _now()
    svc = ServiceDefinition(
        name="Plex", host_label="HOLYGRAIL", host="192.168.10.129",
        port=32400, check_type="http", check_url="/health", enabled=True,
    )
    db.add(svc)
    await db.flush()

    # Old green (20 minutes ago) + recent red (1 minute ago).
    db.add(HealthCheckResult(
        service_id=svc.id,
        checked_at=now - timedelta(minutes=20),
        status="green",
    ))
    db.add(HealthCheckResult(
        service_id=svc.id,
        checked_at=now - timedelta(minutes=1),
        status="red",
        error="down",
    ))
    await db.commit()

    latest = HealthCheckResult(
        service_id=svc.id,
        checked_at=now - timedelta(minutes=1),
        status="red",
        error="down",
    )
    ctx = _ctx(
        session=db,
        services=[svc],
        health_results={svc.id: latest},
        thresholds={"service_down_minutes": Decimal("5")},
        now=now,
    )
    results = await ServiceDownRule().evaluate(ctx)
    assert len(results) == 1
    assert results[0].target_type == "service"
    assert results[0].target_id == svc.id
    assert "Plex" in results[0].message


@pytest.mark.asyncio
async def test_service_down_recent_green_silent(db):
    """Most-recent non-red is INSIDE the window — service has not been
    down long enough, rule must not fire."""
    now = _now()
    svc = ServiceDefinition(
        name="Plex", host_label="HOLYGRAIL", host="192.168.10.129",
        port=32400, check_type="http", check_url="/health", enabled=True,
    )
    db.add(svc)
    await db.flush()

    db.add(HealthCheckResult(
        service_id=svc.id,
        checked_at=now - timedelta(minutes=1),
        status="green",
    ))
    db.add(HealthCheckResult(
        service_id=svc.id,
        checked_at=now,
        status="red",
        error="down",
    ))
    await db.commit()

    latest = HealthCheckResult(
        service_id=svc.id,
        checked_at=now,
        status="red",
    )
    ctx = _ctx(
        session=db,
        services=[svc],
        health_results={svc.id: latest},
        thresholds={"service_down_minutes": Decimal("5")},
        now=now,
    )
    assert await ServiceDownRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_service_down_latest_not_red_silent(db):
    """Latest result is green — rule must not fire even if history contains reds."""
    now = _now()
    svc = ServiceDefinition(
        name="Plex", host_label="HOLYGRAIL", host="192.168.10.129",
        port=32400, check_type="http", check_url="/health", enabled=True,
    )
    db.add(svc)
    await db.flush()
    await db.commit()

    latest = HealthCheckResult(
        service_id=svc.id,
        checked_at=now,
        status="green",
    )
    ctx = _ctx(
        session=db,
        services=[svc],
        health_results={svc.id: latest},
        thresholds={"service_down_minutes": Decimal("5")},
        now=now,
    )
    assert await ServiceDownRule().evaluate(ctx) == []


# ── DeviceOfflineRule ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_device_offline_breaching_fires():
    now = _now()
    device = _device(
        id=10,
        hostname="torrentbox",
        last_seen=now - timedelta(minutes=30),
        first_seen=now - timedelta(days=1),
        is_online=False,
    )
    ctx = _ctx(
        devices=[device],
        thresholds={"device_offline_minutes": Decimal("10")},
        now=now,
    )
    results = await DeviceOfflineRule().evaluate(ctx)
    assert len(results) == 1
    assert results[0].target_id == 10
    assert "torrentbox" in results[0].message


@pytest.mark.asyncio
async def test_device_offline_online_device_silent():
    """An online device with stale last_seen must NOT fire — the rule
    trusts the scanner's is_online flag, with last_seen acting only as a
    grace-period gate. Stale last_seen is common between scanner cycles."""
    now = _now()
    device = _device(
        id=11,
        last_seen=now - timedelta(hours=40),
        first_seen=now - timedelta(days=10),
        is_online=True,
    )
    ctx = _ctx(
        devices=[device],
        thresholds={"device_offline_minutes": Decimal("10")},
        now=now,
    )
    assert await DeviceOfflineRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_device_offline_recent_seen_silent():
    now = _now()
    device = _device(
        id=12,
        last_seen=now - timedelta(minutes=2),
        first_seen=now - timedelta(days=1),
        is_online=False,
    )
    ctx = _ctx(
        devices=[device],
        thresholds={"device_offline_minutes": Decimal("10")},
        now=now,
    )
    assert await DeviceOfflineRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_device_offline_last_seen_none_skipped():
    """Never-seen device: last_seen=None. Must NOT fire even if gap is
    arbitrarily old — this is a first-cycle-after-deploy guard."""
    now = _now()
    device = _device(
        id=13,
        last_seen=now - timedelta(days=365),  # doesn't matter
        first_seen=now - timedelta(days=365),
        is_online=False,
    )
    device.last_seen = None  # type: ignore[assignment]
    ctx = _ctx(
        devices=[device],
        thresholds={"device_offline_minutes": Decimal("10")},
        now=now,
    )
    assert await DeviceOfflineRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_device_offline_first_seen_none_skipped():
    """first_seen=None is also a valid skip path."""
    now = _now()
    device = _device(id=14, is_online=False)
    device.last_seen = now - timedelta(days=365)
    device.first_seen = None  # type: ignore[assignment]
    ctx = _ctx(
        devices=[device],
        thresholds={"device_offline_minutes": Decimal("10")},
        now=now,
    )
    assert await DeviceOfflineRule().evaluate(ctx) == []


# ── OllamaUnavailableRule ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ollama_unavailable_fires_when_unhealthy():
    ctx = _ctx(ollama_healthy=False)
    results = await OllamaUnavailableRule().evaluate(ctx)
    assert len(results) == 1
    assert results[0].target_type == "system"
    assert results[0].target_id is None
    assert "Ollama" in results[0].message


@pytest.mark.asyncio
async def test_ollama_unavailable_silent_when_healthy():
    ctx = _ctx(ollama_healthy=True)
    assert await OllamaUnavailableRule().evaluate(ctx) == []


# ── UnknownDeviceRule ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_device_breaching_fires(db):
    """Same unknown MAC seen in 3 consecutive scans spanning ≥30 minutes."""
    now = _now()

    # Seed three scans 15 minutes apart (span = 30 minutes exactly).
    scans = []
    for i, ago in enumerate([35, 20, 5]):  # oldest -> newest
        s = Scan(
            started_at=now - timedelta(minutes=ago),
            status="completed",
            devices_found=1,
            new_devices=0,
        )
        db.add(s)
        scans.append(s)
    await db.flush()

    # Seed a device row for the unknown MAC (events.device_id joins on Device).
    rogue = Device(
        mac_address="aa:bb:cc:dd:ee:ff",
        ip_address="192.168.10.77",
        hostname=None,
        vendor=None,
        first_seen=now - timedelta(minutes=35),
        last_seen=now - timedelta(minutes=5),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=False,
    )
    db.add(rogue)
    await db.flush()

    for s in scans:
        db.add(Event(
            event_type="device_seen",
            device_id=rogue.id,
            scan_id=s.id,
            timestamp=s.started_at,
            details={},
        ))
    await db.commit()

    # recent_scans expected in DESC order (newest first) per build_context.
    recent = sorted(scans, key=lambda x: x.started_at, reverse=True)
    ctx = _ctx(session=db, recent_scans=recent, now=now)

    results = await UnknownDeviceRule().evaluate(ctx)
    assert len(results) == 1
    r = results[0]
    assert r.target_type == "system"
    assert r.target_id is None
    assert r.rule_id_override == "unknown_device:aa:bb:cc:dd:ee:ff"
    assert "aa:bb:cc:dd:ee:ff" in r.message


@pytest.mark.asyncio
async def test_unknown_device_known_mac_skipped(db):
    """A MAC marked is_known_device=True must be filtered out."""
    now = _now()

    scans = []
    for ago in [35, 20, 5]:
        s = Scan(
            started_at=now - timedelta(minutes=ago),
            status="completed",
            devices_found=1,
            new_devices=0,
        )
        db.add(s)
        scans.append(s)
    await db.flush()

    known = Device(
        mac_address="11:22:33:44:55:66",
        ip_address="192.168.10.200",
        hostname="server",
        vendor=None,
        first_seen=now - timedelta(days=30),
        last_seen=now,
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=True,
    )
    db.add(known)
    await db.flush()

    for s in scans:
        db.add(Event(
            event_type="device_seen",
            device_id=known.id,
            scan_id=s.id,
            timestamp=s.started_at,
            details={},
        ))
    await db.commit()

    recent = sorted(scans, key=lambda x: x.started_at, reverse=True)
    ctx = _ctx(session=db, recent_scans=recent, now=now)
    assert await UnknownDeviceRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_unknown_device_short_span_silent(db):
    """Only 3 scans but total span < 30 minutes — rule must not fire."""
    now = _now()

    scans = []
    for ago in [10, 5, 1]:  # span = 9 minutes
        s = Scan(
            started_at=now - timedelta(minutes=ago),
            status="completed",
            devices_found=1,
            new_devices=0,
        )
        db.add(s)
        scans.append(s)
    await db.flush()

    rogue = Device(
        mac_address="aa:aa:aa:aa:aa:aa",
        ip_address="192.168.10.88",
        hostname=None,
        vendor=None,
        first_seen=now - timedelta(minutes=10),
        last_seen=now - timedelta(minutes=1),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=False,
    )
    db.add(rogue)
    await db.flush()
    for s in scans:
        db.add(Event(
            event_type="device_seen",
            device_id=rogue.id,
            scan_id=s.id,
            timestamp=s.started_at,
            details={},
        ))
    await db.commit()

    recent = sorted(scans, key=lambda x: x.started_at, reverse=True)
    ctx = _ctx(session=db, recent_scans=recent, now=now)
    assert await UnknownDeviceRule().evaluate(ctx) == []


@pytest.mark.asyncio
async def test_unknown_device_too_few_scans_silent(db):
    """Fewer than 3 recent scans total — rule must early-return."""
    now = _now()
    ctx = _ctx(session=db, recent_scans=[], now=now)
    assert await UnknownDeviceRule().evaluate(ctx) == []
