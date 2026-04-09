# Tasks: Network Discovery & Device Inventory

**Input**: Design documents from `/specs/008-network-discovery-inventory/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/rest-api.md ✅, quickstart.md ✅

**Tests**: Test-After per Constitution IV — tests appear after implementation in each story's phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new dependencies and scaffold required before any story work begins.

- [x] T001 [P] Add python-nmap, mac-vendor-lookup, alembic, pytest-asyncio to `advisor/backend/requirements.txt`
- [x] T002 [P] Update `advisor/backend/Dockerfile` — add `RUN apt-get install -y nmap` after existing apt installs
- [x] T003 [P] Add `@tanstack/react-table` to `advisor/frontend/package.json` (run `npm install @tanstack/react-table`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema evolution and Docker Compose changes that all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Initialize Alembic in `advisor/backend/` — run `alembic init migrations`, configure `alembic.ini` to use `DATABASE_URL` env var, configure `migrations/env.py` to import `app.database.Base` and all models
- [x] T005 Write Alembic migration `advisor/backend/migrations/versions/001_network_discovery.py` — implement all schema changes from data-model.md: add `mac_address`, `vendor`, `first_seen`, `last_seen`, `is_online`, `consecutive_missed_scans`, `is_known_device` columns to `devices`; drop `device_type`/`status` columns; replace unique constraints; create `annotations`, `scans`, `events` tables with all indexes; insert 5 pre-populated annotation rows for known Camelot devices
- [x] T006 [P] Update `advisor/backend/app/models/device.py` — replace existing model with new schema: MAC as canonical key, add vendor/timestamps/online-tracking fields; drop `device_type` and `status` mapped columns; keep `services` and `alerts` relationships (FKs survive migration — only the ORM columns, not the FK constraints, are removed)
- [x] T007 [P] Create `advisor/backend/app/models/annotation.py` — SQLAlchemy model: id, device_id (FK unique), role (str, default "unknown"), description (nullable text), tags (ARRAY(String), default []), created_at, updated_at; relationship back to Device
- [x] T008 [P] Create `advisor/backend/app/models/scan.py` — SQLAlchemy model: id, started_at, completed_at (nullable), status (str, default "running"), devices_found (nullable int), new_devices (nullable int, default 0), error_detail (nullable text)
- [x] T009 [P] Create `advisor/backend/app/models/event.py` — SQLAlchemy model: id, event_type (str), device_id (nullable FK → devices.id ON DELETE SET NULL), scan_id (nullable FK → scans.id ON DELETE SET NULL), timestamp (default now()), details (JSON nullable)
- [x] T010 Update `advisor/backend/app/models/__init__.py` — export Device, Annotation, Scan, Event (keep Alert, Service exports)
- [x] T011 Update `advisor/docker-compose.yml` — (a) add `ports: ["127.0.0.1:5432:5432"]` to postgres service so scanner can reach it; (b) add `scanner` service: image built from `./backend`, `command: python scanner_entrypoint.py`, `network_mode: host`, env vars `DATABASE_URL` (using `127.0.0.1:5432`), `SCAN_INTERVAL_SECONDS`, `SCAN_TARGET`, depends_on postgres

**Checkpoint**: Run `alembic upgrade head` against a fresh DB — all tables created, 5 annotation rows seeded. `docker compose config` validates without errors.

---

## Phase 3: User Story 1 — Scan LAN and Populate Device List (Priority: P1) 🎯 MVP

**Goal**: Scanner sidecar performs ARP-based nmap scan of 192.168.10.0/24 every 15 minutes, upserts devices by MAC address into PostgreSQL, and records each scan pass.

**Independent Test**: `docker compose up -d` → wait one scan interval → `curl http://localhost:8000/scans` shows a completed scan with devices_found > 0 → `curl http://localhost:8000/devices` returns all LAN devices with MAC, IP, vendor, last_seen populated.

### Implementation for User Story 1

- [x] T012 [P] [US1] Create `advisor/backend/app/services/scanner.py` — async function `run_scan(db: AsyncSession) -> Scan`: (1) create Scan row with status=running; (2) run `nmap -sn {SCAN_TARGET}` via python-nmap; (3) for each up host: extract ip, mac (nm[host]['addresses'].get('mac')), vendor via mac-vendor-lookup; upsert Device by mac_address (update ip, hostname, vendor, last_seen, is_online=True, consecutive_missed_scans=0); (4) mark devices not in scan results as missed (increment consecutive_missed_scans); (5) update Scan row with status=completed, devices_found, new_devices; return Scan
- [x] T013 [P] [US1] Create `advisor/backend/app/routers/scans.py` — two endpoints: `GET /scans` (query last N scans, default limit 20); `POST /scans/trigger` (insert a Scan row with status="pending" — scanner loop checks for pending rows; return 202 or 409 if scan already running)
- [x] T014 [US1] Create `advisor/backend/scanner_entrypoint.py` — async main loop: (1) connect to DB via asyncpg using `DATABASE_URL` env with `127.0.0.1:5432`; (2) at start of each loop: purge events older than 30 days; check for pending Scan rows; (3) call `run_scan()`; (4) `asyncio.sleep(SCAN_INTERVAL_SECONDS)`; structured JSON logging for scan start/complete/error; handle KeyboardInterrupt for clean shutdown
- [x] T015 [US1] Update `advisor/backend/app/main.py` — register scans router with prefix `/scans`
- [x] T016 [US1] Create `advisor/backend/tests/test_scanner.py` — pytest-asyncio tests: (a) `test_scan_upserts_device_by_mac` — mock python-nmap output with two devices, call `run_scan()`, assert both appear in DB with correct fields; (b) `test_scan_increments_missed_scans` — seed a device, mock scan returning no hosts, call `run_scan()`, assert consecutive_missed_scans=1; (c) `test_scan_failure_does_not_update_devices` — mock nmap raising exception, assert Scan row status=failed, no device status changes

**Checkpoint**: `docker compose up scanner` → logs show "Starting scan", "Scan completed, N devices found". `GET /scans` returns completed scan. `GET /devices` returns discovered devices.

---

## Phase 4: User Story 2 — View Device Inventory in Dashboard (Priority: P2)

**Goal**: Dashboard page at `/devices` lists all known devices with IP, hostname, MAC, vendor, last_seen, online/offline indicator; sortable by any column; filterable by hostname or IP; known Camelot devices visually distinguished.

**Independent Test**: Open `http://advisor.holygrail/devices` — table shows all discovered devices with green/gray status dots; sort by "Last Seen" descending works; typing in filter box narrows the list.

### Implementation for User Story 2

- [x] T017 [US2] Create `advisor/backend/app/routers/devices.py` — two endpoints: `GET /devices` (query params: `online` bool, `sort` str, `order` str, `q` str; return list of device objects with nested annotation); `GET /devices/{mac_address}` (single device by MAC; 404 if not found)
- [x] T018 [US2] Update `advisor/backend/app/main.py` — register devices router with prefix `/devices`
- [x] T019 [P] [US2] Create `advisor/frontend/src/components/StatusDot.tsx` — small colored circle: green when `isOnline=true`, gray when false; tooltip shows "Online" / "Offline"
- [x] T020 [P] [US2] Create `advisor/frontend/src/components/DeviceTable.tsx` — TanStack Table v8: columns (status dot, IP, hostname, MAC, vendor, last_seen); client-side sort on all columns; text filter input bound to `q` (filters hostname and IP); known Camelot devices (`is_known_device=true`) shown with subtle highlight (e.g., Tailwind `bg-blue-50`); loading skeleton while fetching
- [x] T021 [US2] Create `advisor/frontend/src/pages/Devices.tsx` — fetch `GET /api/devices`, pass data to `DeviceTable`; refresh button; page title "Device Inventory"; device count summary line ("12 devices, 10 online")
- [x] T022 [US2] Update `advisor/frontend/src/App.tsx` — add `/devices` route pointing to `Devices` page; add "Devices" nav link in the app header/nav
- [x] T023 [US2] Create `advisor/backend/tests/test_devices_api.py` — pytest-asyncio tests: (a) `test_list_devices_returns_all` — seed 3 devices, GET /devices, assert all 3 returned with annotation nested; (b) `test_filter_by_hostname` — seed devices with different hostnames, GET /devices?q=HOLY, assert only HOLYGRAIL returned; (c) `test_get_device_by_mac` — GET /devices/{mac}, assert correct device; (d) `test_get_device_not_found` — GET /devices/00:00:00:00:00:00, assert 404

**Checkpoint**: Open dashboard `/devices` — table renders, sorting and filtering work, status dots show correctly for online/offline devices.

---

## Phase 5: User Story 3 — Annotate Devices with Roles and Descriptions (Priority: P3)

**Goal**: Clicking any device opens an annotation editor; admin assigns role, description, and tags; saved immediately without a new scan; known Camelot devices start with pre-populated annotations.

**Independent Test**: Click HOLYGRAIL in device list — annotation modal opens pre-populated with role=server. Change description, save — list reflects update immediately without page reload.

### Implementation for User Story 3

- [x] T024 [P] [US3] Add `PATCH /devices/{mac_address}/annotation` endpoint to `advisor/backend/app/routers/devices.py` — accept partial body (role, description, tags all optional); upsert Annotation row for device; return updated device object; 404 if device not found; 422 if role value invalid
- [x] T025 [P] [US3] Create `advisor/frontend/src/components/DeviceAnnotationModal.tsx` — modal triggered by row click in DeviceTable: role dropdown (server/workstation/iot/storage/networking/printer/dns/unknown), description textarea, tags input (comma-separated); pre-populated from device's existing annotation; submit calls `PATCH /api/devices/{mac}/annotation`; close on save or cancel
- [x] T026 [US3] Update `advisor/frontend/src/pages/Devices.tsx` — pass `onRowClick` handler to DeviceTable; manage selected device state; render `DeviceAnnotationModal` when device selected; on save success: refetch device list to reflect updated annotation inline

**Checkpoint**: All 5 Camelot devices show pre-populated roles in annotation modal. Edit and save on any device — change persists after page refresh.

---

## Phase 6: User Story 4 — Detect New and Missing Devices (Priority: P4)

**Goal**: Event log captures new-device (first appearance), offline (2+ missed scans), back-online (return after offline), and scan-error events. Dashboard `/events` page shows full history newest-first. AI context includes last 24h of events.

**Independent Test**: Connect a new device to the LAN → within one scan cycle, `GET /api/events?type=new-device` returns an event with that device's MAC. Disconnect HOLYGRAIL → after 2 scan cycles, `GET /api/events?type=offline` shows an offline event.

### Implementation for User Story 4

- [x] T027 [US4] Extend `advisor/backend/app/services/scanner.py` with event detection logic: (a) after upserting a device found in scan — if `first_seen == last_seen` (brand new): insert Event(type="new-device"); if device was previously `is_online=False`: insert Event(type="back-online"); (b) for each device missing from scan results: increment `consecutive_missed_scans`; if `consecutive_missed_scans == 2` and was online: set `is_online=False`, insert Event(type="offline"); (c) on nmap exception: set Scan status=failed, insert Event(type="scan-error", device_id=None, details={"error": str(e)}); do NOT modify any device statuses
- [x] T028 [P] [US4] Create `advisor/backend/app/routers/events.py` — `GET /events` with query params: `type` (filter by event_type), `since` (ISO 8601 datetime, optional, no default — AI context callers pass this explicitly), `limit` (default 100, max 500), `offset` (default 0); return `{total, events}` with nested device summary for non-scan-error events
- [x] T029 [US4] Update `advisor/backend/app/main.py` — register events router with prefix `/events`
- [x] T030 [P] [US4] Create `advisor/frontend/src/pages/Events.tsx` — fetch `GET /api/events` (no `since` param — fetches full 30-day history, paginated); render events list newest-first; each row shows: timestamp, event_type badge (color-coded: green=new-device/back-online, red=offline, yellow=scan-error), device hostname/IP (or "–" for scan-error), details; pagination if >100 events
- [x] T031 [US4] Update `advisor/frontend/src/App.tsx` — add `/events` route pointing to `Events` page; add "Events" nav link
- [x] T032 [US4] Create `advisor/backend/tests/test_events_api.py` — pytest-asyncio tests: (a) `test_events_returns_newest_first` — seed 3 events with different timestamps, GET /events, assert descending order; (b) `test_filter_by_event_type` — seed mixed event types, GET /events?type=offline, assert only offline events returned; (c) `test_events_since_param` — seed events across time range, GET /events?since=..., assert only recent events returned; (d) `test_scan_error_event_has_null_device` — seed scan-error event, assert device field is null in response

**Checkpoint**: Trigger two consecutive scan errors — `GET /events` shows two scan-error events. Disconnect a device for 2 cycles — offline event appears. Reconnect — back-online event appears.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Environment config, CORS, and final validation.

- [x] T033 [P] Create `advisor/backend/app/routers/ai_context.py` — `GET /ai-context` endpoint: query all devices with their annotations; query events where `timestamp >= NOW() - INTERVAL '24 hours'`; return a single JSON object with two keys: `devices` (list of {mac, ip, hostname, role, description, tags, is_online}) and `events` (list of {event_type, timestamp, device_mac, device_hostname, details}); this endpoint is called by the AI chat feature to populate its system prompt context (covers FR-010 and FR-012)
- [x] T034 [P] Update `advisor/backend/app/main.py` — register ai_context router with prefix `/ai-context`
- [x] T035 [P] Update `advisor/.env.example` — add `SCAN_INTERVAL_SECONDS=900` and `SCAN_TARGET=192.168.10.0/24` with inline comments explaining each
- [x] T036 [P] Update `advisor/backend/app/main.py` CORS config — add `http://advisor.holygrail` to `allow_origins` list alongside existing `http://localhost:5173`
- [x] T037 Run through `specs/008-network-discovery-inventory/quickstart.md` step by step on HOLYGRAIL — note any steps that don't match final implementation and update quickstart.md accordingly

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — all 3 tasks start immediately in parallel
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
  - T004 (alembic init) → T005 (write migration) — sequential
  - T006, T007, T008, T009 (model files) — parallel with each other
  - T010 (models `__init__.py`) — after T006–T009
  - T011 (docker-compose) — parallel with model tasks (different file)
- **User Stories (Phase 3–6)**: All depend on Phase 2 completion; each story phase is sequential
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories. Foundational phase must be complete.
- **US2 (P2)**: Depends on US1 (device data must exist in DB to display). T013 (scanner loop) must be running.
- **US3 (P3)**: Depends on US2 (annotation modal lives in the Devices page). T024 can start in parallel with T025.
- **US4 (P4)**: Depends on US1 scanner infrastructure (T012 must exist to extend in T027). T028/T030 can be developed before T027 if using mock data.

### Within Each User Story

- Implementation tasks come first per Constitution IV (Test-After)
- Models before services (Phase 2 gates this for all stories)
- Services before endpoints
- Backend endpoints before frontend components
- Core implementation before tests

---

## Parallel Examples

### Phase 1 (all parallel)

```text
T001 requirements.txt  |  T002 Dockerfile  |  T003 npm install tanstack
```

### Phase 2 (partial parallel)

```text
T004 alembic init → T005 migration
T006 device model  |  T007 annotation model  |  T008 scan model  |  T009 event model
                        ↓
                    T010 models __init__
T011 docker-compose (any time in phase)
```

### Phase 3 / US1

```text
T012 scanner service  |  T013 scans router
         ↓
    T014 scanner entrypoint → T015 register router → T016 tests
```

### Phase 4 / US2

```text
T017 devices router → T018 register router
T019 StatusDot  |  T020 DeviceTable
                        ↓
                    T021 Devices page → T022 App routes → T023 tests
```

---

## Implementation Strategy

### MVP (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T011)
3. Complete Phase 3: US1 (T012–T016)
4. **STOP and VALIDATE**: `docker compose up -d` → confirm scanner runs, `GET /scans` shows completed scan, `GET /devices` returns real LAN devices
5. Deploy to HOLYGRAIL — inventory data is live

### Incremental Delivery

1. Setup + Foundational → DB schema and containers ready
2. US1 → Scanner running, devices in DB, `/scans` API working (**MVP**)
3. US2 → Dashboard table live at `advisor.holygrail/devices`
4. US3 → Annotation editing works for all devices
5. US4 → Event history and change detection live

---

## Notes

- `[P]` tasks touch different files with no blocking dependencies — safe to work in parallel
- Scanner sidecar connects to postgres via `127.0.0.1:5432` (host networking); backend connects via `postgres:5432` (bridge DNS) — two different `DATABASE_URL` values in docker-compose
- POST /scans/trigger communicates with the scanner via a `pending` Scan row in the DB (polling approach) — no direct network path between bridge-networked backend and host-networked scanner
- All 5 Camelot device annotations seeded in T005 migration — no manual annotation required on first deploy
- Event retention purge (30 days) runs at the top of each scanner loop iteration in T014
