# Research: Device Enrichment & Auto-Identification

**Branch**: `013-device-enrichment` | **Date**: 2026-04-13

## R1: mDNS/Bonjour Library Choice

**Decision**: Use `zeroconf` (pure Python, async-compatible)

**Rationale**: zeroconf is the de facto Python mDNS library. It provides a `ServiceBrowser` that passively listens for service advertisements via a callback interface, and a `Zeroconf` instance that can run in a background thread. It supports async via `AsyncZeroconf`. The library handles mDNS multicast group joining, cache management, and service record parsing. No native extensions or system-level mDNS daemons required.

**Alternatives considered**:
- `python-avahi`: Requires Avahi daemon installed in the container. Adds system dependency and D-Bus complexity. Rejected for simplicity.
- Raw socket mDNS: Would require reimplementing mDNS packet parsing, multicast group management, and cache TTL handling. Rejected — zeroconf already does this well.

**Integration pattern**: Start `Zeroconf()` instance once at scanner boot in `scanner_entrypoint.py`. Register `ServiceBrowser` instances for common service types. Accumulate discoveries in a thread-safe dict keyed by IP. The enrichment pass reads from this cache.

**Key service types to browse**:
- `_airplay._tcp.local.` (Apple AirPlay — speakers, Apple TV)
- `_companion-link._tcp.local.` (Apple devices — iPhone, iPad, Mac)
- `_ipp._tcp.local.` / `_printer._tcp.local.` (printers)
- `_homekit._tcp.local.` (HomeKit accessories)
- `_sonos._tcp.local.` (Sonos speakers)
- `_http._tcp.local.` (generic HTTP services)
- `_smb._tcp.local.` (SMB/CIFS shares)
- `_raop._tcp.local.` (AirPlay audio)
- `_googlecast._tcp.local.` (Chromecast devices)

## R2: nmap OS/Service Fingerprinting Flags

**Decision**: Use `nmap -O -sV --top-ports 100 --host-timeout 30s --script nbstat.nse`

**Rationale**: This combines OS detection (`-O`), service version detection (`-sV`), NetBIOS name resolution (`nbstat.nse`), and limits the scan scope (`--top-ports 100`) for speed. The `--host-timeout 30s` prevents hanging on unresponsive hosts. The existing `python-nmap` library supports all of these flags — no new Python dependency needed.

**Alternatives considered**:
- Full port scan (`-p-`): Too slow for enrichment (can take 10+ minutes per host). Rejected.
- Separate NetBIOS tool (`nbtscan`): Would add a system dependency. The nmap NSE script `nbstat.nse` provides the same data within the existing nmap scan. Rejected.
- `nmap -A` (aggressive scan): Includes traceroute and script scanning beyond what's needed. Rejected for unnecessary overhead.

**Rate limiting**: Max 5 devices per enrichment cycle. Devices are selected by priority: no hostname first, then no OS family, then oldest enrichment timestamp. This keeps each enrichment cycle under ~3 minutes (5 hosts x 30s timeout worst case, plus overhead).

**Root requirement**: `-O` (OS detection) requires root privileges. The scanner container already runs as root for ARP scanning, so no privilege changes are needed.

## R3: SSDP/UPnP Implementation

**Decision**: Use stdlib `socket` for M-SEARCH multicast + `httpx` (already in requirements) for XML fetch

**Rationale**: SSDP is a simple protocol — send a UDP multicast M-SEARCH to `239.255.255.250:1900`, collect responses for 10 seconds, then fetch the device description XML from each responder's `LOCATION` header. No library needed beyond stdlib `socket` and `httpx` (already a dependency). The UPnP XML is parsed with `xml.etree.ElementTree` (stdlib).

**Alternatives considered**:
- `async-upnp-client`: Full UPnP client library. Overkill for discovery-only use case. Rejected for simplicity.
- `ssdpy`: Lightweight SSDP library, but adds a dependency for ~30 lines of socket code. Rejected.

**M-SEARCH payload**:
```
M-SEARCH * HTTP/1.1\r\n
HOST: 239.255.255.250:1900\r\n
MAN: "ssdp:discover"\r\n
MX: 5\r\n
ST: ssdp:all\r\n
\r\n
```

**XML fields to extract** from UPnP device description:
- `<friendlyName>` — display name
- `<manufacturer>` — device manufacturer
- `<modelName>` — model name
- `<modelNumber>` — model number

## R4: Classification Rules Design

**Decision**: Dict-based priority chain with confidence levels

**Rationale**: A simple Python dict maps enrichment signals to roles. Rules are evaluated in priority order: mDNS service type (highest confidence) > open ports > OS family > vendor string (lowest confidence). The first match wins. This is simple, testable, and easily extensible by adding entries to the dict.

**Classification map**:

| Signal Source | Signal | Role | Confidence |
| --- | --- | --- | --- |
| mDNS service | `_ipp._tcp`, `_printer._tcp` | printer | high |
| mDNS service | `_airplay._tcp`, `_raop._tcp`, `_sonos._tcp` | speaker | high |
| mDNS service | `_homekit._tcp` | iot | high |
| mDNS service | `_companion-link._tcp` | iot | high |
| mDNS service | `_googlecast._tcp` | speaker | high |
| mDNS service | `_smb._tcp` | storage | medium |
| Open port | 53 | dns | high |
| Open port | 554 (RTSP) | camera | medium |
| Open port | 80/443 + OS Linux | server | medium |
| Open port | 631 (IPP) | printer | medium |
| OS family | macOS, Windows | workstation | medium |
| OS family | iOS, Android | iot | low |
| Vendor string | contains "sonos" | speaker | medium |
| Vendor string | contains "camera", "hikvision", "dahua" | camera | medium |
| Vendor string | contains "raspberry pi" | server | low |

**Confidence levels**:
- **high**: Strong signal with very low false-positive rate (e.g., specific mDNS service type)
- **medium**: Reasonable inference but could be wrong (e.g., open port 80 on Linux = server)
- **low**: Weak signal, best-guess classification (e.g., OS family alone)

## R5: Annotation Model Extension for Auto-Classification

**Decision**: Add `classification_source` and `classification_confidence` columns to the `annotations` table

**Rationale**: The existing `Annotation` model already stores `role`. Adding `classification_source` (who set the role: "user", "mdns", "nmap", "ssdp", "vendor", or null) and `classification_confidence` ("high", "medium", "low", or null) alongside it keeps the data model simple. When a user manually sets a role via the PATCH endpoint, `classification_source` is set to "user" and `classification_confidence` to null (not applicable). Auto-classification only runs when `classification_source` is not "user".

**Alternatives considered**:
- Separate classification table: Adds a join for every device query. Rejected for simplicity.
- Store classification in Device model instead of Annotation: Would split role-related data across two tables. Rejected — role already lives in Annotation.

## R6: mDNS Listener Lifecycle in Scanner Container

**Decision**: Start `Zeroconf` instance once at scanner boot, keep running across scan cycles

**Rationale**: mDNS is a passive protocol — the listener accumulates discoveries over time. Starting it once and keeping it running means the cache is warm by the time the first enrichment pass runs. The `Zeroconf` instance runs its own background thread for network I/O, so it doesn't block the async scan loop.

**Lifecycle**:
1. `scanner_entrypoint.py` creates `Zeroconf()` and `ServiceBrowser` instances before entering the scan loop
2. mDNS discoveries accumulate in a `dict[str, MdnsInfo]` keyed by IP address
3. `run_enrichment()` reads from this cache after each `run_scan()` completes
4. `Zeroconf.close()` is called on scanner shutdown (KeyboardInterrupt or container stop)

## R7: Enrichment Data on Device Model vs. Separate Table

**Decision**: Add enrichment columns directly to the `devices` table

**Rationale**: Enrichment data is 1:1 with the device record. Adding columns (os_family, os_detail, mdns_name, netbios_name, ssdp_friendly_name, ssdp_model, last_enriched_at, enrichment_ip) to the existing Device model avoids an extra join on every query. This follows the pattern already used for `monitor_offline` (migration 006).

**Alternatives considered**:
- Separate `device_enrichment` table with FK to devices: Adds complexity (extra join, extra model) for no benefit since it's always 1:1. Rejected.
