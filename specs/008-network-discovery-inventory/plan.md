# Implementation Plan: Network Discovery & Device Inventory

**Branch**: `008-network-discovery-inventory` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/008-network-discovery-inventory/spec.md`

## Summary

Extend the F4.1 advisor scaffold with automated LAN scanning (nmap) and a persistent device inventory. The backend gains a scanner sidecar container (host networking for ARP/MAC discovery), Alembic migrations extending the existing schema, REST endpoints for device management, and an event log. The frontend gains a Device Inventory page (sortable/filterable table, online status indicators, annotation editor) and an Event History page.

## Technical Context

**Language/Version**: Python 3.12 (backend + scanner), TypeScript 5.x (frontend)  
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.x, python-nmap 0.7.x, mac-vendor-lookup 0.3.x, APScheduler not used (simple asyncio loop); React 18, Tailwind CSS 3, Vite 5, TanStack Table v8 (sortable list)  
**Storage**: PostgreSQL 16 (existing Docker volume, extended via Alembic migration)  
**Testing**: pytest + pytest-asyncio (backend), Vitest + React Testing Library (frontend)  
**Target Platform**: HOLYGRAIL — Ubuntu 24.04 LTS, x86_64, Docker Compose  
**Project Type**: web-service (extends existing advisor app)  
**Performance Goals**: Device list page loads in <2s; full /24 scan completes in <5 minutes (well within 15-min interval)  
**Constraints**: No external API calls; vendor lookup from bundled OUI database; scanner container requires `network_mode: host` for ARP-based MAC discovery; postgres must expose port to host (`127.0.0.1:5432:5432`) for scanner → DB connection  
**Scale/Scope**: ~255 addresses scanned, ~10–20 devices expected, 30-day event retention (~3K events maximum)

## Constitution Check

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Local-First | ✅ Pass | All scanning and vendor lookup is local. `mac-vendor-lookup` uses a bundled OUI database — no HTTP calls at scan time. No external AI API calls in this feature. |
| II. Simplicity | ✅ Pass | Scanner uses a plain `asyncio.sleep` loop — no APScheduler, no Celery. `python-nmap` wraps system nmap. No repository pattern — direct SQLAlchemy session usage throughout. |
| III. Containerized Everything | ✅ Pass | All code runs in Docker Compose containers. Scanner is a new sidecar service (same Docker image, different entrypoint). `network_mode: host` is required for ARP — not full `--privileged`. |
| IV. Test-After | ✅ Pass | Implementation first, tests after. pytest for scanner service and API endpoints; Vitest for React components. |
| V. Observability | ✅ Pass | Scan-error events logged as structured JSON AND persisted to DB. Scan stats (devices_found, new_devices) stored per-scan. `/health` endpoint unchanged. |

**Violations**: None.

## Project Structure

### Documentation (this feature)

```text
specs/008-network-discovery-inventory/
├── plan.md              # This file
├── research.md          # Phase 0 — architectural decisions
├── data-model.md        # Phase 1 — schema design
├── contracts/
│   └── rest-api.md      # Phase 1 — API contract
├── quickstart.md        # Phase 1 — dev/deploy guide
└── tasks.md             # Phase 2 — created by /speckit.tasks
```

### Source Code (repository root)

```text
advisor/
├── backend/
│   ├── app/
│   │   ├── models/
│   │   │   ├── device.py          # MODIFIED: add mac_address, vendor, timestamps, online tracking
│   │   │   ├── annotation.py      # NEW: role, description, tags (one-to-one with device)
│   │   │   ├── scan.py            # NEW: scan pass records
│   │   │   ├── event.py           # NEW: network change events
│   │   │   ├── alert.py           # UNCHANGED (F4.1)
│   │   │   └── service.py         # UNCHANGED (F4.1)
│   │   ├── routers/
│   │   │   ├── devices.py         # NEW: GET /devices, GET /devices/{mac}, PATCH /devices/{mac}/annotation
│   │   │   ├── events.py          # NEW: GET /events
│   │   │   ├── scans.py           # NEW: GET /scans, POST /scans/trigger
│   │   │   └── health.py          # UNCHANGED (F4.1)
│   │   ├── services/
│   │   │   └── scanner.py         # NEW: nmap scan logic, event detection, 30-day purge
│   │   ├── main.py                # MODIFIED: register new routers
│   │   └── database.py            # UNCHANGED (F4.1)
│   ├── migrations/                # NEW: Alembic migration directory
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 001_network_discovery.py
│   ├── tests/
│   │   ├── test_scanner.py        # NEW: scanner service unit tests
│   │   ├── test_devices_api.py    # NEW: device endpoint tests
│   │   └── test_events_api.py     # NEW: event endpoint tests
│   ├── alembic.ini                # NEW
│   ├── requirements.txt           # MODIFIED: add python-nmap, mac-vendor-lookup, alembic
│   └── Dockerfile                 # MODIFIED: RUN apt-get install -y nmap
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Devices.tsx        # NEW: device inventory page
│       │   └── Events.tsx         # NEW: event history page
│       ├── components/
│       │   ├── DeviceTable.tsx    # NEW: sortable/filterable device list (TanStack Table)
│       │   ├── DeviceAnnotationModal.tsx  # NEW: annotation editor modal
│       │   └── StatusDot.tsx      # NEW: green/gray online indicator
│       └── App.tsx                # MODIFIED: add /devices and /events routes
├── db/
│   └── init.sql                   # UNCHANGED (F4.1 seed schema still valid for fresh deploys)
└── docker-compose.yml             # MODIFIED: add scanner service, expose postgres port
```

**Structure Decision**: Web application (Option 2 from template) — existing `backend/` and `frontend/` separation extended with new scanner service. Tests live in `advisor/backend/tests/` alongside source.

## Complexity Tracking

No constitution violations — table not required.

---

## Key Architecture Decisions

See [research.md](research.md) for full rationale. Summary:

| Decision | Choice | Why |
| -------- | ------ | --- |
| Docker networking for scanner | `network_mode: host` (scanner sidecar) | ARP requires L2 access; bridge NAT blocks it |
| Scanner scheduling | Simple `asyncio.sleep` loop | Scanner is dedicated sidecar; no scheduler overhead needed |
| MAC-to-vendor | `mac-vendor-lookup` (bundled OUI) | Offline, local-first, zero HTTP calls |
| nmap binding | `python-nmap` | Mature wrapper; parses XML output automatically |
| Schema migration | Alembic | Existing DB must evolve in-place without data loss |

## Phase 0: Research ✅

Completed. See [research.md](research.md).

All NEEDS CLARIFICATION items resolved:

- Docker networking strategy → scanner sidecar with `network_mode: host`
- MAC-to-vendor library → `mac-vendor-lookup` (bundled, offline)
- Scheduler approach → simple `asyncio.sleep` loop
- Schema migration approach → Alembic

## Phase 1: Design ✅

Completed. Artifacts:

- [data-model.md](data-model.md) — all 4 tables defined with columns, constraints, indexes, state transitions, migration steps
- [contracts/rest-api.md](contracts/rest-api.md) — 7 endpoints documented with request/response shapes
- [quickstart.md](quickstart.md) — local dev, production deploy, troubleshooting

## Next Step

Run `/speckit.tasks` to generate the implementation task breakdown.
