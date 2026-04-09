"""Tests for the scanner service (test-after, per Constitution IV)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.device import Device
from app.models.event import Event
from app.models.scan import Scan
from app.services.scanner import run_scan


def _make_nmap_result(hosts: list[dict]) -> MagicMock:
    """Build a mock nmap.PortScanner result for the given host list.

    Each host dict: {ip, mac, hostname, vendor}
    """
    nm = MagicMock()
    nm.all_hosts.return_value = [h["ip"] for h in hosts]

    def getitem(ip):
        host = next((h for h in hosts if h["ip"] == ip), None)
        if host is None:
            return {"addresses": {}, "hostnames": [], "vendor": {}}
        item = MagicMock()
        item.get.side_effect = lambda key, default=None: {
            "addresses": {"ipv4": ip, "mac": host.get("mac", "")},
            "hostnames": [{"name": host.get("hostname", "")}] if host.get("hostname") else [],
            "vendor": {host.get("mac", ""): host.get("vendor", "")},
        }.get(key, default)
        item.__getitem__ = lambda self, k: item.get(k)
        return item

    nm.__getitem__ = lambda self, k: getitem(k)
    return nm


@pytest.mark.asyncio
async def test_scan_upserts_device_by_mac(db):
    """Scanner inserts two new devices and records a completed Scan row."""
    hosts = [
        {"ip": "192.168.10.1", "mac": "AA:BB:CC:DD:EE:01", "hostname": "router", "vendor": "Netgear"},
        {"ip": "192.168.10.2", "mac": "AA:BB:CC:DD:EE:02", "hostname": "laptop", "vendor": "Dell"},
    ]
    mock_nm = _make_nmap_result(hosts)

    with patch("app.services.scanner.nmap.PortScanner") as MockScanner:
        MockScanner.return_value = mock_nm
        scan = await run_scan(db, target="192.168.10.0/24")

    assert scan.status == "completed"
    assert scan.devices_found == 2
    assert scan.new_devices == 2

    result = await db.execute(select(Device))
    devices = result.scalars().all()
    macs = {d.mac_address for d in devices}
    assert "AA:BB:CC:DD:EE:01" in macs
    assert "AA:BB:CC:DD:EE:02" in macs

    # Both should have is_online=True
    for d in devices:
        assert d.is_online is True
        assert d.consecutive_missed_scans == 0


@pytest.mark.asyncio
async def test_scan_increments_missed_scans(db):
    """A device present in the DB but absent from scan gets consecutive_missed_scans incremented."""
    existing = Device(
        mac_address="AA:BB:CC:DD:EE:FF",
        ip_address="192.168.10.5",
        hostname="mydevice",
        first_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=False,
    )
    db.add(existing)
    await db.commit()

    # Scan returns no hosts
    mock_nm = _make_nmap_result([])

    with patch("app.services.scanner.nmap.PortScanner") as MockScanner:
        MockScanner.return_value = mock_nm
        await run_scan(db, target="192.168.10.0/24")

    await db.refresh(existing)
    assert existing.consecutive_missed_scans == 1
    # Not yet offline (needs 2 misses)
    assert existing.is_online is True


@pytest.mark.asyncio
async def test_scan_failure_does_not_update_devices(db):
    """When nmap raises an exception, no device statuses are modified and a scan-error event is logged."""
    existing = Device(
        mac_address="BB:CC:DD:EE:FF:00",
        ip_address="192.168.10.10",
        hostname="testdev",
        first_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=False,
    )
    db.add(existing)
    await db.commit()

    with patch("app.services.scanner.nmap.PortScanner") as MockScanner:
        MockScanner.return_value.scan.side_effect = Exception("nmap not found")
        scan = await run_scan(db, target="192.168.10.0/24")

    assert scan.status == "failed"
    assert scan.error_detail is not None

    await db.refresh(existing)
    assert existing.is_online is True
    assert existing.consecutive_missed_scans == 0

    result = await db.execute(select(Event).where(Event.event_type == "scan-error"))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].device_id is None


@pytest.mark.asyncio
async def test_scan_fires_offline_event_at_two_misses(db):
    """Device goes offline after 2 consecutive missed successful scans."""
    existing = Device(
        mac_address="CC:DD:EE:FF:00:01",
        ip_address="192.168.10.20",
        hostname="going-offline",
        first_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        is_online=True,
        consecutive_missed_scans=1,  # already missed once
        is_known_device=False,
    )
    db.add(existing)
    await db.commit()

    mock_nm = _make_nmap_result([])

    with patch("app.services.scanner.nmap.PortScanner") as MockScanner:
        MockScanner.return_value = mock_nm
        await run_scan(db, target="192.168.10.0/24")

    await db.refresh(existing)
    assert existing.is_online is False
    assert existing.consecutive_missed_scans == 2

    result = await db.execute(select(Event).where(Event.event_type == "offline"))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].device_id == existing.id


@pytest.mark.asyncio
async def test_scan_fires_back_online_event(db):
    """Back-online event is fired when an offline device responds."""
    existing = Device(
        mac_address="DD:EE:FF:00:01:02",
        ip_address="192.168.10.30",
        hostname="came-back",
        first_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
        is_online=False,
        consecutive_missed_scans=3,
        is_known_device=False,
    )
    db.add(existing)
    await db.commit()

    hosts = [{"ip": "192.168.10.30", "mac": "DD:EE:FF:00:01:02", "hostname": "came-back"}]
    mock_nm = _make_nmap_result(hosts)

    with patch("app.services.scanner.nmap.PortScanner") as MockScanner:
        MockScanner.return_value = mock_nm
        await run_scan(db, target="192.168.10.0/24")

    await db.refresh(existing)
    assert existing.is_online is True
    assert existing.consecutive_missed_scans == 0

    result = await db.execute(select(Event).where(Event.event_type == "back-online"))
    events = result.scalars().all()
    assert len(events) == 1
