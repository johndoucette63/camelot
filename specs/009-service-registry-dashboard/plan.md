# Implementation Plan: Service Registry & Health Dashboard

**Branch**: `009-service-registry-dashboard` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/009-service-registry-dashboard/spec.md`

## Summary

Build a service health dashboard on top of the existing Network Advisor app. Two new PostgreSQL tables (`service_definitions`, `health_check_results`) track known services and probe history. A background asyncio task (running inside the FastAPI process) polls the Docker socket for container inventory and runs HTTP/TCP health checks against 12 seeded services every 60 seconds. Four new API endpoints expose container state, service status, health history, and a summary count. A new Services page in the React frontend presents the data grouped by host with green/yellow/red status indicators and a click-through detail modal.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x (frontend)  
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg, `docker` SDK (docker-py), React 18, Tailwind CSS 3, TanStack React Table v8  
**Storage**: PostgreSQL 16 (existing `advisor_pgdata` volume, extended via Alembic migration 002)  
**Testing**: pytest + httpx (backend), Vitest + React Testing Library (frontend)  
**Target Platform**: HOLYGRAIL (x86_64 Linux, Docker container)  
**Project Type**: Feature extension of existing web-service (advisor app)  
**Performance Goals**: Dashboard loads in < 3s; health status reflects state changes within 60s  
**Constraints**: Docker socket mounted read-only into backend container; LAN-only (192.168.10.0/24); no external APIs  
**Scale/Scope**: ~12 defined services, ~4 hosts, ~15 Docker containers on HOLYGRAIL

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Local-First | ✅ Pass | All health checks target LAN IPs; Docker socket is local. No external APIs. |
| II. Simplicity & Pragmatism | ✅ Pass | Background task in FastAPI lifespan (no new container); seed-only service defs (no CRUD UI); in-memory container state. No enterprise patterns introduced. |
| III. Containerized Everything | ✅ Pass | All changes are within the existing `backend` container. Docker socket mounted as a volume. No new long-running services added outside Docker Compose. |
| IV. Test-After | ✅ Pass | Implementation first; tests written after to validate behavior. |
| V. Observability | ✅ Pass | Health checker emits structured JSON logs per cycle. `/health` endpoint already exists. New routes participate in existing logging middleware. |

**Post-design re-check**: No violations introduced. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/009-service-registry-dashboard/
├── plan.md              ← This file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── api.md           ← Phase 1 output
└── tasks.md             ← Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code (repository root)

```text
advisor/
├── docker-compose.yml              # Modified: add docker.sock volume to backend
├── backend/
│   ├── requirements.txt            # Modified: add docker>=7.0 package
│   ├── app/
│   │   ├── main.py                 # Modified: lifespan context + health checker task
│   │   ├── models/
│   │   │   ├── service_definition.py   # NEW: ServiceDefinition ORM model
│   │   │   ├── health_check_result.py  # NEW: HealthCheckResult ORM model
│   │   │   └── __init__.py             # Modified: export new models
│   │   └── routers/
│   │       ├── services.py         # NEW: GET /services, GET /services/{id}/history
│   │       ├── containers.py       # NEW: GET /containers
│   │       └── dashboard.py        # NEW: GET /dashboard/summary
│   ├── services/
│   │   └── health_checker.py       # NEW: background task + HTTP/TCP check logic
│   ├── migrations/
│   │   └── versions/
│   │       └── 002_service_registry.py  # NEW: Alembic migration + seed data
│   └── tests/
│       ├── test_health_checker.py   # NEW: unit tests for check logic
│       ├── test_services_api.py     # NEW: API tests for /services endpoints
│       ├── test_containers_api.py   # NEW: API tests for /containers
│       └── test_dashboard_api.py    # NEW: API test for /dashboard/summary
└── frontend/
    └── src/
        ├── App.tsx                  # Modified: add /services route
        ├── types.ts                 # Modified: add ServiceDefinition, HealthCheckResult, ContainerState types
        ├── pages/
        │   └── Services.tsx         # NEW: service registry dashboard page
        └── components/
            ├── DashboardSummary.tsx  # NEW: summary banner ("N/M healthy")
            ├── ServiceTable.tsx      # NEW: grouped-by-host service list with status dots
            ├── ServiceDetailModal.tsx # NEW: click-through modal with health history
            └── ContainerList.tsx     # NEW: container inventory with staleness warning

tests/
└── (backend tests alongside source per existing pattern)
```

**Structure Decision**: Web application (Option 2) — extends existing `advisor/backend/` and `advisor/frontend/` layout. No new top-level directories.

## Complexity Tracking

> No constitution violations to justify.
