# Implementation Plan: Device Enrichment & Auto-Identification

**Branch**: `013-device-enrichment` | **Date**: 2026-04-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/013-device-enrichment/spec.md`

## Summary

The current ARP-only scanner discovers IP and MAC addresses but leaves most devices showing blank hostnames and generic vendor strings. This feature adds a multi-protocol enrichment pass (mDNS, nmap OS/service fingerprinting with NetBIOS, SSDP/UPnP) that runs after each ARP sweep, automatically collecting device names, OS families, open services, and UPnP metadata. A rule-based classifier then assigns device roles (printer, speaker, server, etc.) from the enrichment data. The frontend gains an OS column, auto-classification badges, enrichment detail views, and a per-device re-scan button.

## Technical Context

**Language/Version**: Python 3.12 (backend + scanner), TypeScript 5.7 (frontend)
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, python-nmap 0.7.1, zeroconf (new), Alembic 1.14; React 18, Vite 6, Tailwind CSS 3, TanStack React Table 8
**Storage**: PostgreSQL 16 (existing `advisor_pgdata` volume, extended via Alembic migration 007)
**Testing**: pytest + pytest-asyncio (backend), Vitest (frontend)
**Target Platform**: Linux x86_64 Docker container (scanner on host network), browser (frontend)
**Project Type**: Web service (FastAPI backend + React frontend) with scanner sidecar
**Performance Goals**: Enrichment pass completes in <5 minutes for up to 50 devices
**Constraints**: Scanner runs as root with host networking; max 5 active fingerprints per cycle; per-host timeout 30s; SSDP timeout 10s
**Scale/Scope**: Single subnet (192.168.10.0/24), <50 devices, single admin user

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle                  | Status | Notes                                                                                                                                                            |
| -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| I. Local-First             | PASS   | All enrichment runs locally on the LAN scanner. No cloud APIs, no external services. mDNS/SSDP are LAN-only protocols.                                          |
| II. Simplicity & Pragmatism | PASS   | Rule-based classification (dict lookup) — no ML, no event bus, no abstract factories. Single new file for enrichment logic. zeroconf is the only new dependency. |
| III. Containerized Everything | PASS   | Enrichment runs inside the existing scanner container (host network, root). No new containers.                                                                   |
| IV. Test-After             | PASS   | Implementation first, then pytest tests for enrichment logic and classification rules.                                                                           |
| V. Observability           | PASS   | Enrichment results logged via existing JSON structured logging. Enrichment timestamps stored on device records for monitoring.                                    |
| Technology Stack           | PASS   | Python 3.12 + FastAPI + PostgreSQL + React + Tailwind. zeroconf is a pure-Python mDNS library — no prohibited tech.                                              |
| Development Workflow       | PASS   | Feature branch, direct commits, deploy via existing `deploy-advisor.sh`.                                                                                         |

No violations. No entries needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/013-device-enrichment/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api-endpoints.md
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
advisor/
├── backend/
│   ├── app/
│   │   ├── models/
│   │   │   ├── device.py          # MODIFY — add enrichment columns
│   │   │   ├── annotation.py      # MODIFY — add classification_source, classification_confidence
│   │   │   └── service.py         # EXISTING — reuse for nmap-discovered services
│   │   ├── routers/
│   │   │   └── devices.py         # MODIFY — extend DeviceOut, add re-enrich endpoint
│   │   └── services/
│   │       ├── scanner.py         # EXISTING — unchanged (ARP sweep)
│   │       └── enrichment.py      # NEW — enrichment orchestrator + classifiers
│   ├── migrations/versions/
│   │   └── 007_device_enrichment.py  # NEW — add enrichment columns
│   ├── scanner_entrypoint.py      # MODIFY — call run_enrichment() after run_scan()
│   └── requirements.txt           # MODIFY — add zeroconf
│
├── frontend/src/
│   ├── types.ts                   # MODIFY — extend Device/Annotation interfaces
│   ├── components/
│   │   ├── DeviceTable.tsx         # MODIFY — add OS column, auto-badge, re-scan button
│   │   └── DeviceAnnotationModal.tsx  # MODIFY — add enrichment detail section
│   └── pages/
│       └── Devices.tsx            # MODIFY — wire re-scan handler
│
└── docker-compose.yml             # NO CHANGE — scanner already has host network + root
```

**Structure Decision**: Extends the existing `advisor/` web application structure. Enrichment logic lives in a single new service file (`enrichment.py`). No new containers, no new top-level directories.

## Complexity Tracking

No constitution violations to justify.
