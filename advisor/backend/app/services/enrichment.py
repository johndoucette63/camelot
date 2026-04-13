"""Device enrichment orchestrator.

Runs after each ARP scan cycle to enrich device records with mDNS names,
OS fingerprinting, SSDP/UPnP metadata, and auto-classification.
"""

import asyncio
import logging
import re
import socket
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from urllib.parse import urlparse

import httpx
import nmap
from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.annotation import Annotation
from app.models.device import Device
from app.models.service import Service

logger = logging.getLogger("scanner")

# mDNS service types to browse
MDNS_SERVICE_TYPES = [
    "_airplay._tcp.local.",
    "_companion-link._tcp.local.",
    "_ipp._tcp.local.",
    "_printer._tcp.local.",
    "_homekit._tcp.local.",
    "_sonos._tcp.local.",
    "_http._tcp.local.",
    "_smb._tcp.local.",
    "_raop._tcp.local.",
    "_googlecast._tcp.local.",
]


@dataclass
class MdnsInfo:
    """Collected mDNS data for a single IP address."""
    name: str
    service_types: set[str] = field(default_factory=set)


class MdnsListener:
    """Passive mDNS/Bonjour listener using zeroconf.

    Accumulates service advertisements in a thread-safe dict keyed by IP.
    Start once at scanner boot and keep running across scan cycles.
    """

    def __init__(self) -> None:
        self._cache: dict[str, MdnsInfo] = {}
        self._lock = threading.Lock()
        self._zc: Zeroconf | None = None
        self._browsers: list[ServiceBrowser] = []

    @property
    def cache(self) -> dict[str, MdnsInfo]:
        with self._lock:
            return dict(self._cache)

    def start(self) -> None:
        self._zc = Zeroconf()
        for stype in MDNS_SERVICE_TYPES:
            browser = ServiceBrowser(self._zc, stype, handlers=[self._on_service])
            self._browsers.append(browser)
        logger.info("mDNS listener started", extra={"service_types": len(MDNS_SERVICE_TYPES)})

    def close(self) -> None:
        if self._zc:
            self._zc.close()
            self._zc = None
        self._browsers.clear()
        logger.info("mDNS listener stopped")

    def _on_service(self, zeroconf: Zeroconf, service_type: str, name: str, state_change) -> None:
        """Callback invoked by ServiceBrowser on add/update."""
        try:
            info = zeroconf.get_service_info(service_type, name, timeout=3000)
            if not info or not info.parsed_addresses():
                return

            friendly = parse_mdns_name(name)
            # Strip the trailing ".local." service type suffix for classification
            stype_key = service_type.rstrip(".")

            for addr in info.parsed_addresses():
                with self._lock:
                    existing = self._cache.get(addr)
                    if existing:
                        existing.service_types.add(stype_key)
                        # Keep the first discovered name (usually the best)
                    else:
                        self._cache[addr] = MdnsInfo(
                            name=friendly,
                            service_types={stype_key},
                        )
        except Exception as exc:
            logger.debug("mDNS service info error: %s", exc)


def parse_mdns_name(raw_name: str) -> str:
    """Parse a friendly name from an mDNS service instance name.

    Example: "Johns-iPhone._companion-link._tcp.local." -> "Johns iPhone"
    """
    # Instance name is everything before the service type
    # Format: "<instance>.<service_type>"
    # The instance name is the part before the first "._" that starts a service type
    match = re.match(r"^(.+?)\._[a-zA-Z]", raw_name)
    if match:
        name = match.group(1)
    else:
        name = raw_name

    # Clean up: replace hyphens and underscores with spaces, strip whitespace
    name = name.replace("-", " ").replace("_", " ")
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name


async def run_enrichment(db: AsyncSession, mdns_cache: dict) -> None:
    """Orchestrate all enrichment sources for devices needing enrichment."""
    # Find devices needing enrichment: never enriched or IP changed
    stmt = (
        select(Device)
        .options(selectinload(Device.annotation), selectinload(Device.services))
        .where(
            or_(
                Device.last_enriched_at.is_(None),
                Device.enrichment_ip != Device.ip_address,
            )
        )
    )
    result = await db.execute(stmt)
    devices = list(result.scalars().all())

    if not devices:
        logger.info("Enrichment: no devices need enrichment")
        return

    logger.info("Enrichment: %d devices to enrich", len(devices))

    # Run enrichment sources
    await _enrich_mdns(db, devices, mdns_cache)
    await _enrich_nmap(db, devices)
    await _enrich_ssdp(db, devices)
    await _auto_classify(db, devices)

    # Mark devices as enriched
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for device in devices:
        device.last_enriched_at = now
        device.enrichment_ip = device.ip_address

    await db.commit()
    logger.info("Enrichment finished")


async def _enrich_mdns(
    db: AsyncSession, devices: list[Device], mdns_cache: dict
) -> None:
    """Enrich devices from mDNS cache.

    Matches mDNS discoveries to devices by IP address.
    """
    if not mdns_cache:
        return

    count = 0
    for device in devices:
        info = mdns_cache.get(device.ip_address)
        if not info:
            continue
        if isinstance(info, MdnsInfo):
            device.mdns_name = info.name
            # Store service types for classification (transient attribute)
            device._mdns_service_types = info.service_types  # type: ignore[attr-defined]
            count += 1

    if count:
        logger.info("mDNS cache: %d devices discovered", count)


NMAP_BATCH_SIZE = 5


async def _enrich_nmap(db: AsyncSession, devices: list[Device]) -> None:
    """Enrich devices via nmap OS/service fingerprinting + NetBIOS.

    Selects up to NMAP_BATCH_SIZE devices that lack hostname or OS family,
    prioritizing never-enriched devices. Runs nmap with OS detection, service
    version scanning, and the nbstat NSE script.
    """
    # Select candidates: missing hostname or OS, ordered by least-recently enriched
    candidates = [
        d for d in devices
        if not d.hostname or not d.os_family
    ]
    candidates.sort(key=lambda d: (d.last_enriched_at is not None, d.last_enriched_at))
    targets = candidates[:NMAP_BATCH_SIZE]

    if not targets:
        return

    target_ips = " ".join(d.ip_address for d in targets)
    logger.info("Fingerprinting %d devices", len(targets))

    loop = asyncio.get_event_loop()
    try:
        nm = await loop.run_in_executor(
            None,
            partial(
                _run_nmap_scan,
                target_ips,
            ),
        )
    except Exception as exc:
        logger.warning("nmap fingerprint scan failed: %s", exc)
        return

    ip_to_device = {d.ip_address: d for d in targets}

    for host in nm.all_hosts():
        device = ip_to_device.get(host)
        if not device:
            continue

        # Extract OS information
        os_matches = nm[host].get("osmatch", [])
        if os_matches:
            best = os_matches[0]
            os_detail = best.get("name", "")
            if os_detail:
                device.os_detail = os_detail
                # Derive os_family from the OS class or name
                os_classes = best.get("osclass", [])
                if os_classes:
                    family = os_classes[0].get("osfamily", "")
                    if family:
                        device.os_family = family

        # Extract NetBIOS name from NSE script output
        host_scripts = nm[host].get("hostscript", [])
        for script in host_scripts:
            if script.get("id") == "nbstat":
                output = script.get("output", "")
                nbname = _parse_netbios_name(output)
                if nbname:
                    device.netbios_name = nbname
                break

        # Upsert discovered services
        await _upsert_nmap_services(db, device, nm[host])

    logger.info("Fingerprinted %d devices", len(targets))


def _run_nmap_scan(targets: str) -> nmap.PortScanner:
    """Run nmap scan synchronously (called via run_in_executor)."""
    nm = nmap.PortScanner()
    nm.scan(
        hosts=targets,
        arguments="-O -sV --top-ports 100 --host-timeout 30s --script nbstat.nse",
    )
    return nm


def _parse_netbios_name(nbstat_output: str) -> str | None:
    """Extract the NetBIOS computer name from nbstat NSE output."""
    for line in nbstat_output.splitlines():
        line = line.strip()
        # Look for lines like: "WORKSTATION  <00>  unique"
        if "<00>" in line and "unique" in line.lower():
            parts = line.split()
            if parts:
                return parts[0]
    return None


async def _upsert_nmap_services(
    db: AsyncSession, device: Device, host_data: dict
) -> None:
    """Upsert discovered open ports/services from nmap results."""
    protocols = ("tcp", "udp")
    for proto in protocols:
        ports = host_data.get(proto, {})
        for port_num, port_info in ports.items():
            if port_info.get("state") != "open":
                continue
            svc_name = port_info.get("name", f"{proto}/{port_num}")
            # Upsert by (device_id, name) unique constraint
            result = await db.execute(
                select(Service).where(
                    Service.device_id == device.id,
                    Service.name == svc_name,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.port = int(port_num)
                existing.status = "open"
            else:
                db.add(Service(
                    device_id=device.id,
                    name=svc_name,
                    port=int(port_num),
                    status="open",
                ))


SSDP_MULTICAST = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MX = 5
SSDP_TIMEOUT = 10

SSDP_MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_MULTICAST}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    f"MX: {SSDP_MX}\r\n"
    "ST: ssdp:all\r\n"
    "\r\n"
)

# UPnP XML namespace
UPNP_NS = "{urn:schemas-upnp-org:device-1-0}"


def _ssdp_discover() -> dict[str, str]:
    """Send SSDP M-SEARCH and collect LOCATION URLs keyed by IP.

    Returns {ip_address: location_url}.
    Runs synchronously — call via run_in_executor.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(SSDP_TIMEOUT)

    try:
        sock.sendto(SSDP_MSEARCH.encode(), (SSDP_MULTICAST, SSDP_PORT))
    except OSError as exc:
        logger.debug("SSDP send failed: %s", exc)
        sock.close()
        return {}

    locations: dict[str, str] = {}
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            ip = addr[0]
            # Parse LOCATION header from HTTP-like response
            for line in data.decode(errors="replace").splitlines():
                if line.lower().startswith("location:"):
                    url = line.split(":", 1)[1].strip()
                    locations[ip] = url
                    break
        except socket.timeout:
            break
        except OSError:
            break

    sock.close()
    return locations


async def _fetch_upnp_description(
    client: httpx.AsyncClient, url: str
) -> tuple[str | None, str | None]:
    """Fetch and parse a UPnP device description XML.

    Returns (friendly_name, model_string) or (None, None) on failure.
    """
    try:
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
    except Exception:
        return None, None

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None, None

    device_el = root.find(f"{UPNP_NS}device")
    if device_el is None:
        # Try without namespace
        device_el = root.find("device")
    if device_el is None:
        return None, None

    def _text(tag: str) -> str | None:
        el = device_el.find(f"{UPNP_NS}{tag}")  # type: ignore[union-attr]
        if el is None:
            el = device_el.find(tag)  # type: ignore[union-attr]
        return el.text.strip() if el is not None and el.text else None

    friendly = _text("friendlyName")
    model_name = _text("modelName")
    model_number = _text("modelNumber")

    model_parts = [p for p in (model_name, model_number) if p]
    model_string = " ".join(model_parts) if model_parts else None

    return friendly, model_string


async def _enrich_ssdp(db: AsyncSession, devices: list[Device]) -> None:
    """Enrich devices via SSDP/UPnP discovery.

    Sends M-SEARCH, fetches device descriptions, and matches by IP.
    """
    loop = asyncio.get_event_loop()
    try:
        locations = await loop.run_in_executor(None, _ssdp_discover)
    except Exception as exc:
        logger.debug("SSDP discovery failed: %s", exc)
        return

    if not locations:
        return

    logger.info("SSDP discovery: %d responses", len(locations))

    ip_to_device = {d.ip_address: d for d in devices}
    count = 0

    async with httpx.AsyncClient() as client:
        for ip, url in locations.items():
            device = ip_to_device.get(ip)
            if not device:
                continue

            friendly, model = await _fetch_upnp_description(client, url)
            if friendly:
                device.ssdp_friendly_name = friendly
            if model:
                device.ssdp_model = model
            if friendly or model:
                count += 1

    if count:
        logger.info("SSDP enriched %d devices", count)


# ── Classification rules ────────────────────────────────────────────────

# mDNS service type -> (role, confidence)
MDNS_ROLE_MAP: dict[str, tuple[str, str]] = {
    "_ipp._tcp": ("printer", "high"),
    "_printer._tcp": ("printer", "high"),
    "_airplay._tcp": ("speaker", "high"),
    "_raop._tcp": ("speaker", "high"),
    "_sonos._tcp": ("speaker", "high"),
    "_googlecast._tcp": ("speaker", "high"),
    "_homekit._tcp": ("iot", "high"),
    "_companion-link._tcp": ("iot", "high"),
    "_smb._tcp": ("storage", "medium"),
}

# Port number -> (role, confidence)
PORT_ROLE_MAP: dict[int, tuple[str, str]] = {
    53: ("dns", "high"),
    554: ("camera", "medium"),
    631: ("printer", "medium"),
}

# OS family -> (role, confidence)
OS_ROLE_MAP: dict[str, tuple[str, str]] = {
    "macOS": ("workstation", "medium"),
    "Mac OS X": ("workstation", "medium"),
    "Windows": ("workstation", "medium"),
    "iOS": ("iot", "low"),
    "Android": ("iot", "low"),
}

# Vendor substring (lowercased) -> (role, confidence)
VENDOR_ROLE_MAP: dict[str, tuple[str, str]] = {
    "sonos": ("speaker", "medium"),
    "camera": ("camera", "medium"),
    "hikvision": ("camera", "medium"),
    "dahua": ("camera", "medium"),
    "raspberry pi": ("server", "low"),
}


async def _auto_classify(db: AsyncSession, devices: list[Device]) -> None:
    """Auto-classify device roles from enrichment data.

    Rules are evaluated in priority order: mDNS > ports > OS > vendor.
    Never overwrites user-set roles (classification_source == "user").
    """
    count = 0
    for device in devices:
        # Ensure annotation exists
        if device.annotation is None:
            ann = Annotation(device_id=device.id, role="unknown")
            db.add(ann)
            device.annotation = ann
            await db.flush()

        # Skip user-set roles
        if device.annotation.classification_source == "user":
            continue

        role, source, confidence = _classify_device(device)
        if not role or role == "unknown":
            continue

        device.annotation.role = role
        device.annotation.classification_source = source
        device.annotation.classification_confidence = confidence
        count += 1

    if count:
        logger.info("Auto-classified %d devices", count)


def _classify_device(device: Device) -> tuple[str | None, str | None, str | None]:
    """Evaluate classification rules for a single device.

    Returns (role, source, confidence) or (None, None, None) if no match.
    """
    # 1. mDNS service types (highest priority)
    if device.mdns_name:
        # Check the mdns_cache indirectly — we store service types during enrichment
        # For now, we rely on the _enrich_mdns step having stored mDNS info
        pass  # mDNS classification handled below via _mdns_service_types attr

    # Check mDNS service types if stored on the device
    mdns_services = getattr(device, "_mdns_service_types", set())
    for stype, (role, confidence) in MDNS_ROLE_MAP.items():
        if stype in mdns_services:
            return role, "mdns", confidence

    # 2. Open ports
    if hasattr(device, "services") and device.services:
        device_ports = {s.port for s in device.services if s.port}
        for port, (role, confidence) in PORT_ROLE_MAP.items():
            if port in device_ports:
                return role, "nmap", confidence
        # Special case: HTTP on Linux = server
        if device_ports & {80, 443} and device.os_family and "linux" in device.os_family.lower():
            return "server", "nmap", "medium"

    # 3. OS family
    if device.os_family:
        for os_key, (role, confidence) in OS_ROLE_MAP.items():
            if os_key.lower() in device.os_family.lower():
                return role, "nmap", confidence

    # 4. Vendor string (lowest priority)
    if device.vendor:
        vendor_lower = device.vendor.lower()
        for substr, (role, confidence) in VENDOR_ROLE_MAP.items():
            if substr in vendor_lower:
                return role, "vendor", confidence

    return None, None, None
