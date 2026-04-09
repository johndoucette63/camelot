"""LAN scanner service.

Runs an nmap ping sweep of the target subnet, upserts Device records by MAC
address, detects network events (new-device, offline, back-online, scan-error),
and records each scan pass in the Scan table.
"""

import logging
from datetime import datetime, timezone

import nmap
from mac_vendor_lookup import AsyncMacLookup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.event import Event
from app.models.scan import Scan

logger = logging.getLogger(__name__)

_mac_lookup = AsyncMacLookup()

VALID_ROLES = {
    "server", "workstation", "storage", "networking", "dns", "printer",
    "camera", "sensor", "speaker", "appliance", "iot", "unknown"
}


async def _vendor_for_mac(mac: str) -> str | None:
    """Return vendor string for a MAC address, or None on lookup failure."""
    try:
        return await _mac_lookup.lookup(mac)
    except Exception:
        return None


async def run_scan(db: AsyncSession, target: str = "192.168.10.0/24") -> Scan:
    """Perform one nmap ARP scan pass.

    - Creates a Scan row (status=running)
    - Runs nmap -sn against target
    - Upserts Device rows by MAC address
    - Fires new-device, back-online, and offline events as appropriate
    - Updates Scan row to completed/failed
    - Returns the Scan row
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Create scan record
    scan = Scan(started_at=now, status="running")
    db.add(scan)
    await db.flush()  # get scan.id

    try:
        nm = nmap.PortScanner()
        nm.scan(hosts=target, arguments="-sn")
    except Exception as exc:
        logger.error("nmap scan failed", extra={"error": str(exc), "target": target})
        scan.status = "failed"
        scan.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        scan.error_detail = str(exc)
        db.add(
            Event(
                event_type="scan-error",
                scan_id=scan.id,
                timestamp=scan.completed_at,
                details={"error": str(exc)},
            )
        )
        await db.commit()
        return scan

    # Collect responding hosts: {mac: {ip, hostname, vendor}}
    found_macs: dict[str, dict] = {}
    for host in nm.all_hosts():
        addresses = nm[host].get("addresses", {})
        mac = addresses.get("mac")
        if not mac:
            # nmap doesn't return MAC for the scan host (ARP not used for local host)
            # Skip it — the host is already a known device in the DB
            logger.debug("Skipping host with no MAC (scanner host)", extra={"ip": host})
            continue

        hostname_info = nm[host].get("hostnames", [{}])
        hostname = hostname_info[0].get("name") if hostname_info else None
        vendor = nm[host].get("vendor", {}).get(mac) or await _vendor_for_mac(mac)

        found_macs[mac] = {
            "ip": host,
            "hostname": hostname or None,
            "vendor": vendor,
        }

    responding_macs = set(found_macs.keys())
    new_device_count = 0

    # Upsert each responding device
    for mac, info in found_macs.items():
        result = await db.execute(select(Device).where(Device.mac_address == mac))
        device = result.scalar_one_or_none()
        is_new = device is None

        if is_new:
            device = Device(
                mac_address=mac,
                ip_address=info["ip"],
                hostname=info["hostname"],
                vendor=info["vendor"],
                first_seen=now,
                last_seen=now,
                is_online=True,
                consecutive_missed_scans=0,
                is_known_device=False,
            )
            db.add(device)
            await db.flush()
            new_device_count += 1
            db.add(
                Event(
                    event_type="new-device",
                    device_id=device.id,
                    scan_id=scan.id,
                    timestamp=now,
                    details={"ip": info["ip"], "hostname": info["hostname"]},
                )
            )
        else:
            was_offline = not device.is_online
            device.ip_address = info["ip"]
            if info["hostname"]:
                device.hostname = info["hostname"]
            if info["vendor"] and not device.vendor:
                device.vendor = info["vendor"]
            device.last_seen = now
            device.is_online = True
            device.consecutive_missed_scans = 0

            if was_offline:
                db.add(
                    Event(
                        event_type="back-online",
                        device_id=device.id,
                        scan_id=scan.id,
                        timestamp=now,
                        details={"ip": info["ip"]},
                    )
                )

    # Mark missing devices
    result = await db.execute(select(Device).where(Device.is_online == True))  # noqa: E712
    online_devices = result.scalars().all()

    for device in online_devices:
        if device.mac_address not in responding_macs:
            device.consecutive_missed_scans += 1
            if device.consecutive_missed_scans >= 2:
                device.is_online = False
                db.add(
                    Event(
                        event_type="offline",
                        device_id=device.id,
                        scan_id=scan.id,
                        timestamp=now,
                        details={"consecutive_missed_scans": device.consecutive_missed_scans},
                    )
                )

    # Also increment missed count for devices already offline
    result = await db.execute(
        select(Device).where(
            Device.is_online == False,  # noqa: E712
            Device.mac_address.notin_(responding_macs),
        )
    )
    offline_devices = result.scalars().all()
    for device in offline_devices:
        device.consecutive_missed_scans += 1

    scan.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    scan.status = "completed"
    scan.devices_found = len(responding_macs)
    scan.new_devices = new_device_count

    await db.commit()

    logger.info(
        "Scan completed",
        extra={
            "target": target,
            "devices_found": scan.devices_found,
            "new_devices": new_device_count,
        },
    )
    return scan
