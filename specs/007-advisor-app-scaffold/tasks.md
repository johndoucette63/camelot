# Tasks: Network Advisor Application Scaffold

**Input**: Design documents from `/specs/007-advisor-app-scaffold/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Not included — constitution mandates test-after (Principle IV). Test directories are scaffolded empty; tests will be written after implementation in a follow-up.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory structure and initialize dependency files

- [x] T001 Create project directory structure per plan.md: `advisor/backend/app/routers/`, `advisor/backend/app/models/`, `advisor/backend/tests/`, `advisor/frontend/src/components/`, `advisor/frontend/src/pages/`, `advisor/frontend/src/services/`, `advisor/frontend/tests/`, `advisor/frontend/public/`, `advisor/db/`
- [x] T002 [P] Create backend dependencies in `advisor/backend/requirements.txt` — pin: fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, psycopg2-binary, python-json-logger, pydantic-settings
- [x] T003 [P] Initialize frontend project: `advisor/frontend/package.json` with react, react-dom, react-router-dom, typescript, @vitejs/plugin-react, vite, tailwindcss, postcss, autoprefixer, @types/react, @types/react-dom
- [x] T004 [P] Create `advisor/frontend/tsconfig.json` with strict mode, JSX preserve, path aliases

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core backend infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Create environment template in `advisor/.env.example` with POSTGRES_DB=advisor, POSTGRES_USER=john, POSTGRES_PASSWORD=, DATABASE_URL=, OLLAMA_URL=http://ollama.holygrail, TZ=America/Denver
- [x] T006 Create Pydantic settings in `advisor/backend/app/config.py` — load DATABASE_URL, OLLAMA_URL, TZ from environment with defaults per quickstart.md
- [x] T007 Create async database engine in `advisor/backend/app/database.py` — SQLAlchemy 2.0 async engine from config.DATABASE_URL, async session factory, Base declarative model
- [x] T008 [P] Create Device ORM model in `advisor/backend/app/models/device.py` — fields per data-model.md: id, hostname (unique), ip_address (unique), device_type, status (default "unknown"), created_at, updated_at
- [x] T009 [P] Create Service ORM model in `advisor/backend/app/models/service.py` — fields per data-model.md: id, device_id (FK → Device, cascade delete), name, port (nullable), status (default "unknown"), created_at, updated_at. Unique constraint on (device_id, name)
- [x] T010 [P] Create Alert ORM model in `advisor/backend/app/models/alert.py` — fields per data-model.md: id, device_id (FK → Device, nullable), service_id (FK → Service, nullable), severity, message, acknowledged (default false), created_at
- [x] T011 Create model barrel exports in `advisor/backend/app/models/__init__.py` — import and re-export Device, Service, Alert, Base
- [x] T012 Create `advisor/backend/app/__init__.py` (empty) and `advisor/backend/app/routers/__init__.py` (empty)
- [x] T013 Create FastAPI app factory in `advisor/backend/app/main.py` — configure JSON structured logging via python-json-logger, create FastAPI app with /api prefix, register health router (placeholder), add CORS middleware for local dev

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Single-Command Application Deployment (Priority: P1) MVP

**Goal**: `docker compose up` starts backend, frontend, and postgres; accessible at `advisor.holygrail` via Traefik

**Independent Test**: Run `docker compose up -d` from `advisor/`, then `curl http://advisor.holygrail/api/health` returns 200. Browse `http://advisor.holygrail` and see the frontend. `docker compose ps` shows 3 healthy services.

### Implementation for User Story 1

- [x] T014 [US1] Create backend Dockerfile in `advisor/backend/Dockerfile` — python:3.12-slim base, copy requirements.txt, pip install, copy app/, CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
- [x] T015 [P] [US1] Create frontend nginx config in `advisor/frontend/nginx.conf` — serve static files from /usr/share/nginx/html, proxy /api/ requests to backend:8000, SPA fallback (try_files $uri /index.html)
- [x] T016 [P] [US1] Create frontend Dockerfile in `advisor/frontend/Dockerfile` — Stage 1: node:20-alpine, npm install, npm run build. Stage 2: nginx:alpine, copy build output to /usr/share/nginx/html, copy nginx.conf
- [x] T017 [US1] Create Docker Compose in `advisor/docker-compose.yml` — 3 services: postgres (postgres:16-alpine, named volume advisor_pgdata, mount db/init.sql to /docker-entrypoint-initdb.d/, healthcheck), backend (build ./backend, depends_on postgres healthy, env DATABASE_URL), frontend (build ./frontend, Traefik labels: advisor.holygrail → port 80, depends_on backend). External network holygrail-proxy. All services restart: unless-stopped.

**Checkpoint**: `docker compose up -d` starts full stack, accessible at `advisor.holygrail`

---

## Phase 4: User Story 2 — Backend Health Verification (Priority: P2)

**Goal**: `GET /health` returns deep health status including database connectivity check

**Independent Test**: With stack running, `curl http://advisor.holygrail/api/health` returns `{"status":"ok","database":"connected"}`. Stop postgres, re-check: returns 503 with `{"status":"degraded","database":"disconnected"}`.

### Implementation for User Story 2

- [x] T018 [US2] Create health router in `advisor/backend/app/routers/health.py` — GET /health endpoint per contracts/api.md: attempt async DB connection (SELECT 1), return 200 `{"status":"ok","database":"connected"}` on success, return 503 `{"status":"degraded","database":"disconnected"}` on failure. Use database.py engine.
- [x] T019 [US2] Wire health router into app in `advisor/backend/app/main.py` — import and include health router with /health prefix

**Checkpoint**: Health endpoint works with deep DB check, returns correct status codes

---

## Phase 5: User Story 3 — Frontend Development Environment (Priority: P3)

**Goal**: Vite + React + Tailwind project scaffolded with styled landing page, dev proxy to backend, hot reload working

**Independent Test**: Run `npm run dev` from `advisor/frontend/`, open `http://localhost:5173`, see styled landing page. Edit Home.tsx — changes appear without refresh. Click a link to `/api/health` — proxied to backend.

### Implementation for User Story 3

- [x] T020 [P] [US3] Create Vite config in `advisor/frontend/vite.config.ts` — React plugin, dev server proxy: /api → http://localhost:8000 (local dev) or http://backend:8000 (Docker)
- [x] T021 [P] [US3] Create Tailwind config in `advisor/frontend/tailwind.config.js` — content paths: ./index.html, ./src/**/*.{ts,tsx}
- [x] T022 [P] [US3] Create PostCSS config in `advisor/frontend/postcss.config.js` — tailwindcss + autoprefixer plugins
- [x] T023 [P] [US3] Create Tailwind CSS entry in `advisor/frontend/src/index.css` — @tailwind base, components, utilities directives
- [x] T024 [US3] Create HTML entry in `advisor/frontend/index.html` — root div, script src main.tsx, title "Network Advisor"
- [x] T025 [US3] Create app entry in `advisor/frontend/src/main.tsx` — render App component into root, import index.css
- [x] T026 [US3] Create root component in `advisor/frontend/src/App.tsx` — React Router shell with route to Home page
- [x] T027 [US3] Create landing page in `advisor/frontend/src/pages/Home.tsx` — styled with Tailwind: "Network Advisor" heading, brief description, link to health endpoint, Camelot branding. Show connection status indicator.

**Checkpoint**: Frontend loads with Tailwind styling, dev mode has hot reload, /api proxied to backend

---

## Phase 6: User Story 4 — Persistent Data Storage (Priority: P4)

**Goal**: PostgreSQL initialized with schema for Device, Service, Alert tables and seeded with 5 Camelot network devices

**Independent Test**: `docker compose up -d`, then `docker compose exec postgres psql -U john -d advisor -c "SELECT hostname, ip_address FROM devices;"` returns 5 rows. `docker compose down && docker compose up -d`, re-run query — same 5 rows.

### Implementation for User Story 4

- [x] T028 [US4] Create database init script in `advisor/db/init.sql` — CREATE TABLE devices, services, alerts per data-model.md (matching ORM models). INSERT seed data: 5 Camelot devices (HOLYGRAIL/192.168.10.129/server, Torrentbox/192.168.10.141/raspberry_pi, NAS/192.168.10.105/raspberry_pi, Pi-hole DNS/192.168.10.150/raspberry_pi, Mac Workstation/192.168.10.145/workstation). All status = 'unknown'.

**Checkpoint**: Database has 3 tables with correct constraints and 5 seed devices on first boot

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [x] T029 [P] Add .gitignore entries in `advisor/.gitignore` — .env, __pycache__, node_modules, .venv, dist/, build/
- [x] T030 [P] Add Pi-hole DNS entry for advisor.holygrail → 192.168.10.129 (or document /etc/hosts fallback in quickstart.md)
- [x] T031 Run full quickstart.md validation: deploy stack on HOLYGRAIL, verify all 5 checks from quickstart.md Verify table (compose ps, health endpoint, frontend loads, data persists, seed data query)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — creates the deployment infrastructure
- **US2 (Phase 4)**: Depends on Foundational (uses database.py) — can run parallel with US1
- **US3 (Phase 5)**: Depends on Setup (package.json) — can run parallel with US1 and US2
- **US4 (Phase 6)**: No code dependencies — can run parallel with US1, US2, US3 (just a SQL file)
- **Polish (Phase 7)**: Depends on ALL user stories complete

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2 (needs Dockerfiles to wrap backend/frontend)
- **US2 (P2)**: Depends on Phase 2 (needs database.py, main.py)
- **US3 (P3)**: Depends on Phase 1 (needs package.json, tsconfig)
- **US4 (P4)**: No code dependencies (standalone SQL file), but logically tested via US1's docker-compose

### Within Each User Story

- Models before services
- Services before endpoints
- Config files before application code
- Dockerfile after source code exists
- Docker Compose after all Dockerfiles exist

### Parallel Opportunities

**Phase 1**: T002, T003, T004 can all run in parallel (different files)
**Phase 2**: T008, T009, T010 can run in parallel (independent model files)
**Phase 3-6**: US3 and US4 can start as soon as Phase 1 completes. US1 and US2 need Phase 2.
**Phase 5**: T020, T021, T022, T023 can all run in parallel (independent config files)

---

## Parallel Example: Foundational Phase

```text
# After T007 (database.py) completes, launch all models together:
Task T008: "Create Device ORM model in advisor/backend/app/models/device.py"
Task T009: "Create Service ORM model in advisor/backend/app/models/service.py"
Task T010: "Create Alert ORM model in advisor/backend/app/models/alert.py"
```

## Parallel Example: User Story 3

```text
# Launch all config files together:
Task T020: "Create Vite config in advisor/frontend/vite.config.ts"
Task T021: "Create Tailwind config in advisor/frontend/tailwind.config.js"
Task T022: "Create PostCSS config in advisor/frontend/postcss.config.js"
Task T023: "Create Tailwind CSS entry in advisor/frontend/src/index.css"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T013)
3. Complete Phase 3: US1 — Deployment (T014-T017)
4. **STOP and VALIDATE**: `docker compose up -d` works, all 3 services run
5. Deploy to HOLYGRAIL if ready

### Incremental Delivery

1. Setup + Foundational → Backend and frontend codebases initialized
2. Add US1 (Deployment) → Stack runs via `docker compose up` (MVP!)
3. Add US2 (Health) → `/health` endpoint verifies backend + DB
4. Add US3 (Frontend) → Styled landing page at `advisor.holygrail`
5. Add US4 (Database) → Schema + seed data on first boot
6. Polish → DNS entry, gitignore, full quickstart validation

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Constitution: test-after — no test tasks included; test dirs scaffolded empty
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
