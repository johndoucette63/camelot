# Research: Network Discovery & Device Inventory

**Feature**: 008-network-discovery-inventory  
**Date**: 2026-04-09

---

## Decision 1: Docker Networking Strategy for nmap/ARP Scanning

**Decision**: Scanner sidecar container with `network_mode: host`

**Rationale**: MAC address discovery requires ARP, which is a Layer 2 protocol that does not cross Docker bridge NAT. From inside a bridge-networked container, ICMP pings are masqueraded through the host NIC — the ARP entries on the host belong to the host, not the container. The only clean path to ARP from within Docker is `network_mode: host`, which gives the container direct access to the host's network stack and kernel ARP cache.

The existing backend must stay on the `advisor` bridge network because the frontend nginx proxies to `backend:8000` using Docker DNS. Switching the backend to host networking would break `proxy_pass http://backend:8000/`. Therefore, a dedicated scanner sidecar is introduced — same backend Docker image, different entrypoint, host networking.

**Alternatives considered**:
- Bridge + `cap_add: [NET_RAW, NET_ADMIN]` — Can do ICMP ping sweeps and TCP SYN scans, but cannot obtain MAC addresses via ARP. Rejected because MAC is the canonical device identity key.
- Mount `/proc/net/arp` from host — The host ARP table won't contain entries from bridge-masqueraded container traffic. Rejected.
- External cron on HOLYGRAIL host — Decoupled but requires managing separate host-side scripts outside Docker. Rejected for added complexity.

---

## Decision 2: Scanner Loop Architecture (APScheduler vs simple asyncio loop)

**Decision**: Simple `asyncio.sleep` loop inside a standalone Python script

**Rationale**: The scanner is a dedicated sidecar with exactly one job — run a scan, sleep, repeat. APScheduler adds dependency weight and complexity (job stores, scheduler lifecycle) that is only justified when scheduling is embedded alongside other concerns (e.g., inside a FastAPI app that also serves requests). A plain `while True: await run_scan(); await asyncio.sleep(interval)` is fully observable, trivially testable, and requires zero additional dependencies.

**Alternatives considered**:
- APScheduler with AsyncIOScheduler embedded in backend — Would require backend to have host networking OR a separate trigger mechanism. Rejected; scan and API serving are separate concerns.
- Celery + Redis — Enterprise-grade task queue. Completely disproportionate for one scheduled job on a home server. Rejected per Constitution II.

---

## Decision 3: MAC-to-Vendor Lookup

**Decision**: `mac-vendor-lookup` Python package (PyPI)

**Rationale**: Ships with a bundled OUI (Organizationally Unique Identifier) database snapshot. Does not make any HTTP calls at runtime — lookups are pure offline dictionary lookups against the bundled data. Zero external dependency at scan time. Satisfies Constitution I (Local-First).

**Alternatives considered**:
- `netaddr` — Larger package; vendor lookup feature is secondary to its IP address manipulation API. Adds more than needed.
- `manuf` — Similar approach; less actively maintained.
- Manual OUI file download on container build — More work; `mac-vendor-lookup` already handles this.

---

## Decision 4: Schema Evolution Strategy

**Decision**: Alembic migrations with a `migrations/` directory inside `advisor/backend/`

**Rationale**: The F4.1 schema (`devices`, `services`, `alerts`) is already deployed with seed data. This feature requires significant changes to `devices` (add `mac_address`, `vendor`, `first_seen`, `last_seen`, `is_online`, `consecutive_missed_scans`) and three new tables (`annotations`, `scans`, `events`). Alembic provides reversible, versioned migrations that can be applied on deploy without data loss.

The existing `init.sql` (used by PostgreSQL's `docker-entrypoint-initdb.d/` on first boot) will not re-run on an existing volume. Migration scripts are the correct mechanism for in-place evolution.

**Alternatives considered**:
- Recreate DB from scratch — Destroys seed data and any future production data. Rejected.
- Direct `ALTER TABLE` in a second `init.sql` — init scripts only run once (on empty DB). Won't work for existing deployments. Rejected.

---

## Decision 5: nmap Python Binding

**Decision**: `python-nmap` library (wraps system `nmap` binary via subprocess)

**Rationale**: Mature, well-documented wrapper. Handles XML output parsing from nmap automatically. ARP scan with host networking returns MAC addresses in the parsed result under the `addresses` key (`{'ipv4': '...', 'mac': '...'}`) and vendor info under `vendor`. No need to parse nmap XML manually.

**nmap install**: `RUN apt-get install -y nmap` in backend Dockerfile.

**Scan command**: `nmap -sn 192.168.10.0/24` — ping scan that includes ARP for local subnet when running with host networking. With host networking, nmap runs with sufficient privileges to send ARP packets.

**Gotcha**: MAC addresses are returned in nmap XML as a separate `<address addrtype="mac">` element. `python-nmap` exposes this as `nm[host]['addresses'].get('mac')`. Hosts that don't respond will not appear in results at all (nmap only lists up hosts in `-sn` output).
