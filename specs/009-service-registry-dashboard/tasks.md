# Tasks: Service Registry & Health Dashboard

**Input**: Design documents from `specs/009-service-registry-dashboard/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api.md ✅, quickstart.md ✅

**Tests**: Written after implementation per Constitution Principle IV (Test-After).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependency and infrastructure changes required before any implementation can begin.

- [x] T001 Add `docker>=7.0` to advisor/backend/requirements.txt
- [x] T002 Add Docker socket volume mount (`/var/run/docker.sock:/var/run/docker.sock:ro`) to the `backend` service in advisor/docker-compose.yml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database models, migration, and background task skeleton that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 [P] Create `ServiceDefinition` SQLAlchemy ORM model in advisor/backend/app/models/service_definition.py — columns: id, name, host_label, host, port, check_type, check_url, check_interval_seconds, degraded_threshold_ms, enabled, created_at; unique constraint on (name, host); indexes on (host_label) and (enabled)
- [x] T004 [P] Create `HealthCheckResult` SQLAlchemy ORM model in advisor/backend/app/models/health_check_result.py — columns: id, service_id (FK→service_definitions CASCADE), checked_at, status, response_time_ms, error; indexes on (service_id, checked_at DESC) and (checked_at)
- [x] T005 Export `ServiceDefinition` and `HealthCheckResult` in advisor/backend/app/models/__init__.py (depends on T003, T004)
- [x] T006 Write Alembic migration `002_service_registry` in advisor/backend/migrations/versions/002_service_registry.py — up: create service_definitions table, create health_check_results table, insert 12 seed service definitions (HOLYGRAIL: Plex/32400/http, Ollama/11434/http, Grafana/3000/http, Portainer/9000/http, Traefik/8080/tcp, Advisor/8000/http; Torrentbox: Deluge/8112/http, Sonarr/8989/http, Radarr/7878/http, Prowlarr/9696/http; NAS: SMB/445/tcp; Pi-hole DNS: Pi-hole/80/http); down: drop both tables (depends on T005)
- [x] T007 Create advisor/backend/app/services/health_checker.py with async background task skeleton — `async def run_health_checker(app)` infinite loop with 60s sleep, `async def fetch_containers(docker_client)` stub returning container dicts, `async def check_service(svc)` stub returning `("green", None, None)`, `async def purge_old_results(db)` stub; structured JSON log on each cycle start/end
- [x] T008 Update `lifespan` context in advisor/backend/app/main.py — on startup: initialize `app.state.docker = docker.from_env()`, initialize `app.state.container_state = {"running": [], "stopped": [], "refreshed_at": None, "socket_error": True}`, initialize `app.state.hosts_unreachable = set()`, start `asyncio.create_task(run_health_checker(app))`; on shutdown: cancel task and close docker client (depends on T007). Note: routers are registered in their respective user story phases (T011, T022, T031).

**Checkpoint**: Database schema created, health checker task starts (with stubs), app boots cleanly.

---

## Phase 3: User Story 1 — View All Local Containers (Priority: P1) 🎯 MVP

**Goal**: Docker containers running on HOLYGRAIL are visible in the dashboard — name, image, status, ports, uptime — with running and stopped shown separately. Stale data shown with warning when socket is unavailable.

**Independent Test**: Start the advisor, open `/services`, confirm containers match `docker ps` output on HOLYGRAIL. Stop a container, wait 60s, confirm it moves to the stopped section.

### Implementation

- [x] T009 [US1] Implement `fetch_containers(docker_client)` in advisor/backend/app/services/health_checker.py — call `asyncio.to_thread(docker_client.containers.list, all=True)`, map each container to `{id, name, image, status, ports, uptime, created}`; split into running vs stopped lists; update `app.state.container_state`; on `docker.errors.DockerException` set `socket_error=True` and preserve last known containers
- [x] T010 [US1] Create advisor/backend/app/routers/containers.py — `GET /containers` endpoint that reads and returns `app.state.container_state`; no DB access needed
- [x] T011 [US1] Register containers router at prefix `/containers` in advisor/backend/app/main.py
- [x] T012 [P] [US1] Add `ContainerInfo` and `ContainerState` TypeScript interfaces to advisor/frontend/src/types.ts — ContainerInfo: `{id, name, image, status, ports, uptime, created}`; ContainerState: `{running, stopped, refreshed_at, socket_error}`
- [x] T013 [P] [US1] Create advisor/frontend/src/components/ContainerList.tsx — two sections (Running / Stopped); each row shows name, image, status badge, ports, uptime; renders a yellow warning banner when `socket_error=true` with `refreshed_at` timestamp; empty state message when no containers
- [x] T014 [US1] Create advisor/frontend/src/pages/Services.tsx — page skeleton with `<ContainerList>` section; fetches `GET /api/containers` on mount and on a 60s polling interval (depends on T012, T013)
- [x] T015 [US1] Add `/services` route mapped to `<Services>` page in advisor/frontend/src/App.tsx
- [x] T016 [P] [US1] Write pytest tests for `GET /containers` in advisor/backend/tests/test_containers_api.py — `test_returns_container_state_when_healthy` (mock app.state with populated data), `test_returns_stale_data_with_socket_error_flag` (socket_error=true, non-empty containers), `test_returns_empty_on_first_boot` (refreshed_at=null, socket_error=true)
- [x] T016a [P] [US1] Write Vitest + RTL tests for ContainerList in advisor/frontend/src/components/__tests__/ContainerList.test.tsx — `renders running containers list`, `renders stopped containers separately`, `shows staleness warning banner when socket_error is true`, `shows empty state when no containers`

**Checkpoint**: Visit `/services`, see Docker containers grouped by running/stopped. Stale warning appears when socket is unavailable.

---

## Phase 4: User Story 2 — Check Service Health Status (Priority: P2)

**Goal**: Each defined service is probed every 60 seconds. Dashboard shows green/yellow/red status. Clicking a service shows health history.

**Independent Test**: Stop Plex on HOLYGRAIL. Wait 60 seconds. Confirm Plex row turns red in the dashboard. Restart Plex. Confirm it turns green on next cycle. Click Plex row and confirm history shows the red→green transition.

### Implementation

- [x] T017 [US2] Implement `check_http(host, port, check_url, degraded_threshold_ms)` in advisor/backend/app/services/health_checker.py — use `httpx.AsyncClient` with a 10s timeout; measure response time; return `("green", ms, None)` if HTTP 200 within threshold, `("yellow", ms, None)` if HTTP 200 but over threshold, `("red", None, error_str)` on non-200 or exception
- [x] T018 [US2] Implement `check_tcp(host, port)` in advisor/backend/app/services/health_checker.py — use `asyncio.open_connection` with 5s timeout; return `("green", ms, None)` on success, `("red", None, error_str)` on `OSError` or `asyncio.TimeoutError`
- [x] T019 [US2] Implement full health check loop in `run_health_checker()` in advisor/backend/app/services/health_checker.py — query all enabled ServiceDefinitions, call `check_http` or `check_tcp` per service based on check_type, write HealthCheckResult rows to DB via `async_session`, emit structured log per check result (depends on T017, T018)
- [x] T020 [US2] Implement `purge_old_results(db)` in advisor/backend/app/services/health_checker.py — delete HealthCheckResult rows where `checked_at < NOW() - INTERVAL '7 days'`; call once per loop cycle
- [x] T021 [P] [US2] Create advisor/backend/app/routers/services.py — `GET /services`: select all enabled ServiceDefinitions with their latest HealthCheckResult (DISTINCT ON service_id ORDER BY checked_at DESC subquery); return `ServiceWithLatest[]`; `GET /services/{id}/history`: return HealthCheckResult list for service filtered by `hours` param (default 24, max 168), 404 if service not found
- [x] T022 [US2] Register services router at prefix `/services` in advisor/backend/app/main.py
- [x] T023 [P] [US2] Add `ServiceDefinition`, `HealthCheckResult`, `ServiceWithLatest` TypeScript interfaces to advisor/frontend/src/types.ts
- [x] T024 [P] [US2] Create advisor/frontend/src/components/HealthStatusBadge.tsx — renders a colored dot + label for `"green"` (green), `"yellow"` (yellow), `"red"` (red), `null` (gray, "Pending"); accepts `status: string | null` prop
- [x] T025 [P] [US2] Create advisor/frontend/src/components/ServiceDetailModal.tsx — modal showing service name, host_label, host, port, check_type; scrollable list of health history entries (checked_at, HealthStatusBadge, response_time_ms or error); fetches `GET /api/services/{id}/history` on open; closes on backdrop or X button
- [x] T026 [US2] Create advisor/frontend/src/components/ServiceTable.tsx — services grouped by host_label; each group is a labeled section; each row shows: name, port, `<HealthStatusBadge>`, last check time; click row opens `<ServiceDetailModal>`; fetches `GET /api/services` on mount with 60s polling interval (depends on T023, T024, T025)
- [x] T027 [US2] Update advisor/frontend/src/pages/Services.tsx to include `<ServiceTable>` section below `<ContainerList>` (depends on T026)
- [x] T028 [P] [US2] Write pytest tests for health check logic in advisor/backend/tests/test_health_checker.py — `test_check_http_green` (mock httpx 200 fast), `test_check_http_yellow` (mock httpx 200 slow >2000ms), `test_check_http_red_non200` (mock httpx 503), `test_check_http_red_timeout` (mock httpx timeout), `test_check_tcp_green` (mock asyncio.open_connection success), `test_check_tcp_red` (mock OSError)
- [x] T029 [P] [US2] Write pytest tests for `/services` endpoints in advisor/backend/tests/test_services_api.py — `test_list_services_returns_latest_status`, `test_list_services_pending_when_no_results`, `test_history_default_24h`, `test_history_custom_hours`, `test_history_clamps_at_168h`, `test_history_404_unknown_service`
- [x] T029a [P] [US2] Write Vitest + RTL tests in advisor/frontend/src/components/__tests__/ — `HealthStatusBadge.test.tsx`: renders correct color for green/yellow/red/null; `ServiceTable.test.tsx`: renders services grouped by host, clicking row opens detail modal; `ServiceDetailModal.test.tsx`: renders health history list with status badges

**Checkpoint**: Every defined service shows a colored status dot. Click any service to see its health history.

---

## Phase 5: User Story 3 — At-a-Glance System Health Summary (Priority: P2)

**Goal**: Summary banner at the top of the Services page shows overall health count ("N/M services healthy") with per-host breakdown.

**Independent Test**: Mark Deluge as down (stop the container on Torrentbox or inject a red result). Reload the page. Confirm the summary changes from "12/12" to "11/12" and the Torrentbox host count updates.

### Implementation

- [x] T030 [US3] Create advisor/backend/app/routers/dashboard.py — `GET /dashboard/summary`: compute total/healthy/degraded/down/unchecked counts from latest HealthCheckResult per ServiceDefinition; include per-host breakdown array; return `DashboardSummary` schema
- [x] T031 [US3] Register dashboard router at prefix `/dashboard` in advisor/backend/app/main.py
- [x] T032 [P] [US3] Add `HostSummary` and `DashboardSummary` TypeScript interfaces to advisor/frontend/src/types.ts
- [x] T033 [P] [US3] Create advisor/frontend/src/components/DashboardSummary.tsx — top banner with "N/M services healthy" headline; color-coded count pills (green healthy, yellow degraded, red down); collapsible per-host breakdown row; fetches `GET /api/dashboard/summary` with 60s polling
- [x] T034 [US3] Update advisor/frontend/src/pages/Services.tsx to render `<DashboardSummary>` at the top of the page, above `<ServiceTable>` and `<ContainerList>` (depends on T033)
- [x] T035 [P] [US3] Write pytest tests for `GET /dashboard/summary` in advisor/backend/tests/test_dashboard_api.py — `test_all_healthy`, `test_mixed_statuses`, `test_unchecked_services_counted`, `test_per_host_breakdown_correct`
- [x] T035a [P] [US3] Write Vitest + RTL tests for DashboardSummary in advisor/frontend/src/components/__tests__/DashboardSummary.test.tsx — `renders N/M healthy headline`, `renders color-coded status pills`, `renders per-host breakdown`

**Checkpoint**: Summary banner visible at top of Services page with accurate counts. Counts update within 60s of a status change.

---

## Phase 6: User Story 4 — Monitor Remote Pi Services (Priority: P3)

**Goal**: Remote Pi services (already seeded in migration 002) are health-checked and grouped correctly. When an entire remote host is unreachable, a host-level alert is shown instead of individual red rows.

**Independent Test**: Disable the network route to Torrentbox (or mock all Torrentbox checks as red connection-refused errors). Confirm the dashboard shows a host-level alert for "Torrentbox" rather than 4 individual red rows.

### Implementation

- [x] T036 [US4] Add host-level unreachability detection to advisor/backend/app/services/health_checker.py — after running all checks per host, if ALL services for a host returned `"red"` with a connection error (not HTTP error), add that host_label to a `hosts_unreachable` set stored on `app.state`
- [x] T037 [US4] Update `GET /dashboard/summary` in advisor/backend/app/routers/dashboard.py to include `hosts_unreachable: list[str]` from `app.state` in the response
- [x] T038 [P] [US4] Update advisor/frontend/src/components/DashboardSummary.tsx — when `hosts_unreachable` is non-empty, render a red alert banner listing unreachable hosts above the per-host breakdown
- [x] T039 [P] [US4] Update advisor/frontend/src/components/ServiceTable.tsx — accept `hostsUnreachable: string[]` prop (passed from Services.tsx via the dashboard summary response); when a host_label appears in `hostsUnreachable`, replace its individual service rows with a single host-level "unreachable" alert row
- [x] T040 [P] [US4] Update advisor/backend/tests/test_dashboard_api.py — add `test_host_level_unreachable_when_all_services_connection_error` and `test_host_not_unreachable_when_some_services_respond`
- [x] T040a [P] [US4] Write Vitest + RTL tests in advisor/frontend/src/components/__tests__/ — `DashboardSummary.test.tsx`: renders red alert banner when hosts_unreachable is non-empty; `ServiceTable.test.tsx`: replaces service rows with host-level unreachable alert row

**Checkpoint**: Torrentbox/NAS/Pi-hole DNS services appear in dashboard. Entire-host failures show a host-level alert, not individual red rows.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Navigation, observability, and end-to-end validation.

- [x] T041 Add "Services" nav link to the existing navigation in advisor/frontend/src/App.tsx (alongside existing Devices / Events links)
- [x] T042 Verify structured JSON log output in advisor/backend/app/services/health_checker.py — confirm log lines include `event`, `service`, `status`, `duration_ms` fields on each check; confirm `event=health_check_cycle_complete` with `checked` count and total `duration_ms`
- [x] T043 Run quickstart.md validation steps end-to-end — apply migration, start stack, hit all 4 new API endpoints, confirm Services page renders with real data

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user story work**
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2/US3/US4
- **US2 (Phase 4)**: Depends on Phase 2 — no dependency on US1 (different files); can run in parallel with US1
- **US3 (Phase 5)**: Depends on Phase 4 (needs health check data for summary counts)
- **US4 (Phase 6)**: Depends on Phase 4 (remote services use same health checker); depends on Phase 5 (host-level alert goes into dashboard summary)
- **Polish (Phase 7)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Start after Phase 2 — independent of US2/US3/US4
- **US2 (P2)**: Start after Phase 2 — independent of US1 (separate files); US3 depends on US2 data
- **US3 (P2)**: Start after US2 complete — needs HealthCheckResult data for counts
- **US4 (P3)**: Start after US2 + US3 — extends both the checker and summary

### Within Each Phase

- Tasks marked [P] within the same phase have no file conflicts — launch together
- Models before services, services before endpoints
- Backend endpoints before frontend components that call them
- Implementation before tests (Constitution Principle IV: Test-After)

### Parallel Opportunities

```
Phase 2:  T003 ║ T004 (different model files)
              ↓
           T005 → T006 → T007 → T008

Phase 3:  T009 → T010 → T011
          T012 ║ T013 (different files, no deps)
          T014 → T015
          T016  (tests, after impl)

Phase 4:  T017 ║ T018 (different check functions)
          T019 → T020 (sequential in health_checker.py)
          T021 ║ T023 ║ T024 ║ T025 (different files)
          T026 → T027
          T028 ║ T029 (different test files)

Phase 5:  T030 → T031
          T032 ║ T033 (different files)
          T034
          T035 (tests, after impl)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) — 2 tasks
2. Complete Phase 2 (Foundational) — 6 tasks
3. Complete Phase 3 (US1) — 8 tasks
4. **STOP and VALIDATE**: `docker ps` output matches dashboard container list; stale warning appears when socket is killed
5. Deploy to HOLYGRAIL — container inventory is live

### Incremental Delivery

1. **After Phase 3** → Container inventory dashboard (MVP)
2. **After Phase 4** → Full health check system with history
3. **After Phase 5** → Summary banner ("N/M healthy")
4. **After Phase 6** → Full network coverage including Pis with host-level alerts
5. Each phase adds value without breaking previous phases

---

## Notes

- [P] tasks have no file conflicts — safe to run in parallel
- [Story] label maps each task to its user story for traceability
- Tests are placed **after** implementation in each phase (Constitution IV: Test-After)
- `httpx` is already in requirements.txt — use `httpx.AsyncClient` for HTTP checks
- Docker socket mount in docker-compose.yml is read-only (`:ro`) — sufficient for `containers.list`
- Seed data in migration 002 covers both local (HOLYGRAIL) and remote (Torrentbox/NAS/Pi-hole) services; US4 requires no additional seed work
- Commit after each checkpoint to leave the system in a working state
