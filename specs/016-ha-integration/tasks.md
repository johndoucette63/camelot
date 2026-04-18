---
description: "Task list for feature 016-ha-integration"
---

# Tasks: Home Assistant Integration

**Input**: Design documents from `/Users/jd/Code/camelot/specs/016-ha-integration/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Per Constitution IV (Test-After), pytest and Vitest test files for this feature are authored **after** the code they validate, not before. Test tasks therefore appear at the end of each user-story phase — after implementation, before checkpoint. The final quickstart run in Phase 6 is the authoritative end-to-end acceptance gate.

**Organization**: Tasks are grouped by user story in spec priority order (P1 → P2 → P2). US-1 is the MVP and delivers standalone value (HA entity visibility in the advisor + unified device inventory) without US-2 or US-3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different file(s), no dependency on an incomplete task
- **[Story]**: US1 (entity state + inventory merge), US2 (Thread view + border-router rule), US3 (notification forwarding)

## Path Conventions

All paths are repo-relative to `/Users/jd/Code/camelot/`.

- [advisor/backend/app/](../../advisor/backend/app/) — Python backend (FastAPI)
- [advisor/backend/migrations/versions/](../../advisor/backend/migrations/versions/) — Alembic migrations
- [advisor/backend/tests/](../../advisor/backend/tests/) — pytest
- [advisor/frontend/src/](../../advisor/frontend/src/) — React + TypeScript
- [advisor/frontend/src/components/__tests__/](../../advisor/frontend/src/components/__tests__/) — Vitest
- [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) — topology documentation

Live deployment is via `bash scripts/deploy-advisor.sh` (rsync+SSH to HOLYGRAIL) per reference memory — never `git pull` on HOLYGRAIL.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Baseline documentation, dependency wiring, and env-var scaffolding. Everything here must land before the migration runs.

- [X] T001 Record the current Home Assistant deployment in [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) per quickstart Step 0: HA host IP and hostname, HA core version, active integrations (HomeKit, Aqara, Thread, MQTT, others), identified Thread border routers and their physical location, known Thread pairing/fragmentation issues. Commit on this feature branch.
- [X] T002 [P] Add `cryptography>=42` to [advisor/backend/requirements.txt](../../advisor/backend/requirements.txt) (only new Python dependency per plan). Pin to a major version consistent with the Python 3.12 base image.
- [X] T003 [P] Append four new env vars to [advisor/.env.example](../../advisor/.env.example): `ADVISOR_ENCRYPTION_KEY=` (no default, required at startup), `HA_POLL_INTERVAL_SECONDS=60`, `HA_REQUEST_TIMEOUT_SECONDS=10`, `HA_NOTIFY_RETRY_BUDGET_SECONDS=300`. Include a header comment explaining how to generate the Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
- [X] T004 [P] Extend [advisor/backend/app/config.py](../../advisor/backend/app/config.py) with the four settings from T003. `advisor_encryption_key` uses `pydantic.SecretStr` with no default; the three HA tunables have the defaults shown. Validate the encryption key is a 32-byte URL-safe base64 Fernet key at load time (raise at startup if missing or malformed — Constitution V: silent failures unacceptable).
- [X] T005 Generate a Fernet key for local development and paste it into a developer `advisor/.env` (gitignored). Record the production rotation procedure (generate new key, back up old key, re-save HA connection to re-encrypt, never commit) in [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) under the new "Home Assistant Integration" subsection.

**Checkpoint**: Dependencies declared, env-var surface ready, doc baseline in place. Migration can now be written.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migration and the cross-story utility modules that every user story depends on. Without this phase, no story can proceed.

**⚠️ CRITICAL**: Phase 2 must complete before US-1, US-2, or US-3 begin.

- [X] T006 Write Alembic migration [advisor/backend/migrations/versions/008_home_assistant_integration.py](../../advisor/backend/migrations/versions/008_home_assistant_integration.py) per [data-model.md](data-model.md): (a) `CREATE TABLE home_assistant_connections` seeded with a single `id=1` row where every other column is `NULL`; (b) `CREATE TABLE ha_entity_snapshots`; (c) `CREATE TABLE thread_border_routers`; (d) `CREATE TABLE thread_devices`; (e) `ALTER TABLE devices ADD COLUMN ha_device_id TEXT NULL, ADD COLUMN ha_connectivity_type TEXT NULL, ADD COLUMN ha_last_seen_at TIMESTAMPTZ NULL`; (f) `ALTER TABLE devices ALTER COLUMN mac_address DROP NOT NULL` + drop the existing table-level unique constraint on `mac_address` + `CREATE UNIQUE INDEX devices_mac_address_unique ON devices (mac_address) WHERE mac_address IS NOT NULL` + add `CHECK (mac_address IS NOT NULL OR ha_device_id IS NOT NULL)` (name this constraint explicitly so the downgrade can drop it); (g) `CREATE UNIQUE INDEX devices_ha_device_id_unique ON devices (ha_device_id) WHERE ha_device_id IS NOT NULL`; (h) `ALTER TABLE notification_sinks ADD COLUMN home_assistant_id INTEGER NULL REFERENCES home_assistant_connections(id) ON DELETE SET NULL`; (i) `ALTER TABLE alerts ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'pending', ADD COLUMN delivery_attempt_count INTEGER NOT NULL DEFAULT 0, ADD COLUMN delivery_last_attempt_at TIMESTAMPTZ NULL, ADD COLUMN delivery_next_attempt_at TIMESTAMPTZ NULL`. Author a correct `downgrade()` that reverses each step in inverse order.
- [X] T007 [P] Create [advisor/backend/app/security.py](../../advisor/backend/app/security.py) — a thin Fernet wrapper exposing `encrypt_token(plaintext: str) -> bytes` and `decrypt_token(ciphertext: bytes) -> str`, plus `mask_token(plaintext: str) -> str` that returns `"…<last 4 chars>"` for redacted read-back. The module reads the key from `settings.advisor_encryption_key`. On decrypt failure raise a dedicated `TokenDecryptionError` so callers can map it to an operator-visible error.
- [X] T008 [P] Create [advisor/backend/app/models/home_assistant_connection.py](../../advisor/backend/app/models/home_assistant_connection.py) per [data-model.md](data-model.md). Singleton enforcement lives in code (service layer), not in the schema — the model itself is a normal `Base` subclass.
- [X] T009 [P] Create [advisor/backend/app/models/ha_entity_snapshot.py](../../advisor/backend/app/models/ha_entity_snapshot.py). Use `JSONB` (`sqlalchemy.dialects.postgresql.JSONB`) for the `attributes` column.
- [X] T010 [P] Create [advisor/backend/app/models/thread_border_router.py](../../advisor/backend/app/models/thread_border_router.py) and [advisor/backend/app/models/thread_device.py](../../advisor/backend/app/models/thread_device.py). `ThreadDevice.parent_border_router_id` is a FK to `thread_border_routers.ha_device_id` with `ondelete="SET NULL"`.
- [X] T011 Extend [advisor/backend/app/models/device.py](../../advisor/backend/app/models/device.py): add `ha_device_id: Mapped[str | None]`, `ha_connectivity_type: Mapped[str | None]`, `ha_last_seen_at: Mapped[datetime | None]`; change `mac_address` and `ip_address` typing to `Mapped[str | None]`. Depends on T006. ⚠ Verify no caller assumes `mac_address` is non-null (grep the codebase and fix as needed — typically scanner code paths, device-list APIs, existing `UniqueConstraint` declarations).
- [X] T012 Extend [advisor/backend/app/models/notification_sink.py](../../advisor/backend/app/models/notification_sink.py): add `home_assistant_id: Mapped[int | None]` as FK to `home_assistant_connections.id`. Leave existing `type`/`endpoint`/`min_severity` columns unchanged; the `type = "home_assistant"` variant stores the notify service name (e.g., `mobile_app_pixel9`) in `endpoint`.
- [X] T013 Extend [advisor/backend/app/models/alert.py](../../advisor/backend/app/models/alert.py): add `delivery_status: Mapped[str]` (default `"pending"`), `delivery_attempt_count: Mapped[int]` (default `0`), `delivery_last_attempt_at: Mapped[datetime | None]`, `delivery_next_attempt_at: Mapped[datetime | None]`.
- [X] T014 Run the migration locally against a dev copy of `advisor_pgdata` (`alembic upgrade head`); verify the existing devices table accepts NULL mac_address via a manual SQL insert of a Thread-shaped row, then rolls back. If `alembic downgrade -1` fails, fix the migration before proceeding.

**Checkpoint**: Schema + models + security helper ready. All user-story phases can begin.

---

## Phase 3: User Story 1 — See IoT device state in the advisor dashboard (Priority: P1) 🎯 MVP

**Goal**: The advisor connects to Home Assistant, polls the filtered entity set on a 60 s cadence, exposes the snapshot via `GET /ha/entities`, shows it in a new **Home Assistant** dashboard tab, and merges HA-known devices into the unified inventory (deduped by MAC/IP, new Thread-only rows keyed by `ha_device_id`).

**Independent Test**: Run quickstart Steps 1, 2, and 4. This delivers the foundational feature — HA device visibility and a unified inventory — without any Thread UI or notification forwarding.

**Scope maps to**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-023, FR-024, FR-025, FR-026, FR-027, FR-028, FR-029, FR-030 · SC-001, SC-004, SC-005, SC-008.

### Implementation for User Story 1

- [X] T015 [P] [US1] Create [advisor/backend/app/services/ha_client.py](../../advisor/backend/app/services/ha_client.py) — `httpx.AsyncClient`-based wrapper around HA REST: `async def ping()` → hits `GET /api/`, `async def states()` → `GET /api/states`, `async def config()` → `GET /api/config`, `async def services()` → `GET /api/services`, `async def call_notify(service: str, payload: dict)` → `POST /api/services/notify/{service}`. All methods take a `HomeAssistantConnection` and raise one of four classified exceptions (`HAAuthError`, `HAUnreachableError`, `HAUnexpectedPayloadError`, `HAOKResponse`) per [research.md](research.md) R8. Timeout = `settings.ha_request_timeout_seconds`. The client decrypts the token via `security.decrypt_token` and caches the decrypted value only for the lifetime of a single call.
- [X] T016 [US1] Create [advisor/backend/app/schemas/home_assistant.py](../../advisor/backend/app/schemas/home_assistant.py) with Pydantic v2 models: `HAConnectionRead` (configured/base_url/token_masked/status/last_success_at/last_error/last_error_at), `HAConnectionUpsert` (base_url/access_token), `HAEntityOut` (fields per [contracts/home-assistant-api.md](contracts/home-assistant-api.md) §2), `HAEntitiesResponse` (connection_status/polled_at/stale/entities[]). No token field ever serializes into response models.
- [X] T017 [US1] Create [advisor/backend/app/services/ha_poller.py](../../advisor/backend/app/services/ha_poller.py) — background async loop that wakes every `settings.ha_poll_interval_seconds`. On each cycle: load the singleton connection; skip if `base_url` is NULL; call `ha_client.states()`; filter entities per the curated allowlist (research R2 — `device_tracker`, select `binary_sensor`/`sensor` by `device_class`, `switch`, `update`, any `thread`-integration entity); upsert matching rows into `ha_entity_snapshots`; delete snapshot rows for entities no longer in HA; update `home_assistant_connections` with `last_success_at` or `last_error` + `last_error_at` per R8 classes; emit a structured JSON log line with counts and duration (Constitution V). Skip the cycle cleanly when the connection row is unconfigured.
- [X] T018 [US1] Create [advisor/backend/app/services/ha_inventory_merge.py](../../advisor/backend/app/services/ha_inventory_merge.py) — pure function `async def merge_ha_devices(session, ha_entities, connection)` invoked at the end of each poll cycle. For each distinct `ha_device_id` in the snapshot: (a) derive connectivity type from the entity mix (any `thread`-integration entity → `thread`; else look up LAN presence by resolving the device's IP attribute → `lan_wifi`/`lan_ethernet`; otherwise `other`); (b) if the device resolves a LAN MAC or IP, try to match an existing `devices` row by MAC (preferred) or IP, and attach `ha_device_id` + `ha_connectivity_type` to that row (FR-027); (c) else upsert a new `devices` row keyed by `ha_device_id` with `mac_address = NULL`, `ip_address = NULL`, `ha_connectivity_type` set (FR-028); (d) update `ha_last_seen_at` to now on every matched/created row. On connection delete (FR-029), a separate function `clear_ha_provenance(session)` wipes `ha_device_id` and `ha_connectivity_type` from every row, and leaves rows without a scanner trail to fall through the existing stale-device pipeline. For HA rebuild (FR-030), the normal merge path re-resolves by LAN match and creates fresh Thread rows — no cross-instance ID mapping attempted.
- [X] T019 [US1] Edit [advisor/backend/app/main.py](../../advisor/backend/app/main.py) — on startup, launch `ha_poller.run()` as an asyncio task alongside the existing `health_checker` and `rule_engine` tasks. On shutdown, cancel the task and await its stop.
- [X] T020 [US1] Create [advisor/backend/app/routers/home_assistant.py](../../advisor/backend/app/routers/home_assistant.py) implementing `GET /ha/entities` per [contracts/home-assistant-api.md](contracts/home-assistant-api.md) §2 (with `domain`, `search`, `stale_only` query params). Response includes `stale=true` when the current connection is in error state. Register the router in `main.py`.
- [X] T021 [US1] Extend [advisor/backend/app/routers/settings.py](../../advisor/backend/app/routers/settings.py) with the three connection endpoints per [contracts/home-assistant-api.md](contracts/home-assistant-api.md) §1: `GET /settings/home-assistant`, `PUT /settings/home-assistant`, `POST /settings/home-assistant/test-connection`, `DELETE /settings/home-assistant`. PUT performs a live validation via `ha_client.ping()` before persisting; on any non-`ok` outcome, return 400 and **do not** persist. DELETE nulls the singleton's columns (does not delete the row), cancels any active HA poller cycle, and invokes `clear_ha_provenance` once. GET returns `token_masked` never the plaintext.
- [X] T022 [P] [US1] Create [advisor/frontend/src/services/homeAssistant.ts](../../advisor/frontend/src/services/homeAssistant.ts) — fetch wrappers for `/settings/home-assistant` (GET/PUT/POST test/DELETE) and `/ha/entities`. Typed against new interfaces in [advisor/frontend/src/types.ts](../../advisor/frontend/src/types.ts).
- [X] T023 [P] [US1] Extend [advisor/frontend/src/types.ts](../../advisor/frontend/src/types.ts) with `HAConnection`, `HAEntity`, `HAEntitiesResponse`, `HAConnectionStatus` (union of `"ok" | "auth_failure" | "unreachable" | "unexpected_payload" | "not_configured"`).
- [X] T024 [US1] Create [advisor/frontend/src/components/HAConnectionForm.tsx](../../advisor/frontend/src/components/HAConnectionForm.tsx) — controlled form with `baseUrl` + `accessToken` inputs, a **Test Connection** button that calls `POST /settings/home-assistant/test-connection` and renders the classified status, and a **Save** button that PUTs. Already-saved state shows `token_masked` in a disabled field with a **Replace token** toggle that clears the mask and reveals the access-token input again. Explicit error copy per status class.
- [X] T025 [US1] Create [advisor/frontend/src/components/HAEntityTable.tsx](../../advisor/frontend/src/components/HAEntityTable.tsx) — TanStack React Table v8 over `HAEntity[]`, columns: friendly name, domain, state, last changed (relative time), with domain filter pills across the top and a `stale`-banner when `HAEntitiesResponse.stale === true` showing `polled_at`.
- [X] T026 [US1] Create [advisor/frontend/src/pages/HomeAssistant.tsx](../../advisor/frontend/src/pages/HomeAssistant.tsx) — page with two subsections: connection status card (reads `GET /settings/home-assistant`), and `HAEntityTable` (reads `GET /ha/entities` every 60 s via `setInterval` or the existing data-fetch hook pattern used on `Devices.tsx`). On first visit with no configured connection, prompt the user to open **Settings → Home Assistant**.
- [X] T027 [US1] Edit [advisor/frontend/src/pages/Settings.tsx](../../advisor/frontend/src/pages/Settings.tsx) to mount `<HAConnectionForm />` as a new section.
- [X] T028 [US1] Edit [advisor/frontend/src/App.tsx](../../advisor/frontend/src/App.tsx) to register a `/home-assistant` route and a nav link. Match the existing nav styling for Devices / Services / Alerts.
- [X] T029 [US1] Edit [advisor/frontend/src/pages/Devices.tsx](../../advisor/frontend/src/pages/Devices.tsx) to add an **HA** column showing the connectivity type pill (`wifi`/`ethernet`/`thread`/`zigbee`/`other`) or `—` when no HA provenance. Ensure devices with `mac_address === null` still render — currently the column likely expects a MAC; show `—` for that cell.
- [X] T029a [US1] Create [advisor/backend/app/services/rules/ha_connection_health.py](../../advisor/backend/app/services/rules/ha_connection_health.py) per FR-023 + FR-024 + Constitution V. The rule runs on each rule-engine cycle, reads the singleton `home_assistant_connections` row, and emits at most one active alert whose severity is determined by `last_error` class: `auth_failure` → severity `critical` with message "Home Assistant authentication failed — rotate the token in Settings → Home Assistant"; `unreachable` → severity `warning` with message "Home Assistant is unreachable — snapshot may be stale"; `unexpected_payload` → severity `warning` with message "Home Assistant returned an unexpected response — check the base URL". `target_type="ha_connection"`, `target_id=1` (the singleton). The alert auto-resolves when the connection returns to `ok`. The rule is a no-op when the connection is not configured (`base_url IS NULL`). Register the rule in [advisor/backend/app/services/rules/__init__.py](../../advisor/backend/app/services/rules/__init__.py). Existing dedup / cool-down semantics from 011 apply unchanged.
- [X] T029b [US1] Extend [advisor/backend/app/routers/dashboard.py](../../advisor/backend/app/routers/dashboard.py) (the existing summary endpoint that powers the home page) to include an `integrations.home_assistant` block: `{ configured: bool, status: "ok"|"auth_failure"|"unreachable"|"unexpected_payload"|"not_configured", last_success_at: iso8601|null, last_error: string|null }`. Satisfies FR-025. Do NOT include `rolling error rate` (spec was tightened in this pass — single-snapshot is sufficient). Frontend consumes this for the nav status pill; no new React work required if the existing `NavStatusPill.tsx` already reads the summary shape.

### Tests for User Story 1 (Test-After per Constitution IV)

- [X] T030 [P] [US1] [advisor/backend/tests/test_security_fernet.py](../../advisor/backend/tests/test_security_fernet.py) — encrypt/decrypt round-trip, `mask_token` shape, `TokenDecryptionError` on wrong-key, startup failure on missing env var.
- [X] T031 [P] [US1] [advisor/backend/tests/test_ha_client.py](../../advisor/backend/tests/test_ha_client.py) — use `httpx.MockTransport` to assert each method maps 200→ok, 401→HAAuthError, 5xx/timeout→HAUnreachableError, non-JSON 200→HAUnexpectedPayloadError.
- [X] T032 [P] [US1] [advisor/backend/tests/test_ha_poller.py](../../advisor/backend/tests/test_ha_poller.py) — one cycle with mocked client: snapshot rows upserted, entities no longer present get deleted, `home_assistant_connections.last_success_at` advances, error class recorded when client raises.
- [X] T033 [P] [US1] [advisor/backend/tests/test_ha_inventory_merge.py](../../advisor/backend/tests/test_ha_inventory_merge.py) — four scenarios: (a) HA device with MAC matches an existing scanner-discovered row → single merged row; (b) HA device with no LAN presence → new row with `mac_address=NULL`; (c) HA reinstall → new `device_id` creates fresh rows, old `ha_device_id`s still present but `ha_last_seen_at` stops advancing; (d) connection delete → `clear_ha_provenance` nulls HA columns, rows without scanner trail still exist pending normal stale-device cleanup.
- [X] T034 [P] [US1] [advisor/backend/tests/test_ha_settings_api.py](../../advisor/backend/tests/test_ha_settings_api.py) — PUT with bad token → 400 + `status="auth_failure"` + nothing persisted; PUT with good token (via mock) → 200 + row populated + `token_masked` returned; GET never returns the plaintext token; DELETE nulls the row and stops the poller (inject a fake poller to assert cancel).
- [X] T035 [P] [US1] [advisor/backend/tests/test_ha_endpoints.py](../../advisor/backend/tests/test_ha_endpoints.py) — `GET /ha/entities` returns filtered entities, respects `domain` filter, sets `stale=true` when the connection is in an error state.
- [X] T036 [P] [US1] [advisor/frontend/src/components/__tests__/HAConnectionForm.test.tsx](../../advisor/frontend/src/components/__tests__/HAConnectionForm.test.tsx) — renders masked token when configured, reveals input when **Replace token** clicked, renders four distinct status pills for the four classes.
- [X] T037 [P] [US1] [advisor/frontend/src/components/__tests__/HAEntityTable.test.tsx](../../advisor/frontend/src/components/__tests__/HAEntityTable.test.tsx) — filters by domain, shows stale banner when `stale=true`, handles empty `entities[]`.
- [X] T037a [P] [US1] [advisor/backend/tests/test_rule_ha_connection_health.py](../../advisor/backend/tests/test_rule_ha_connection_health.py) — covers T029a: `last_error=None` → no alert; `last_error="auth_failure"` → one active alert, severity `critical`, correct message; `last_error="unreachable"` → severity `warning`; `last_error="unexpected_payload"` → severity `warning`; transition back to `last_error=None` auto-resolves the active alert; unconfigured connection (`base_url IS NULL`) → no alert emitted; consecutive cycles with the same error do not create duplicate alerts (dedup via existing `(rule_id, target_id)` semantics).
- [X] T037b [P] [US1] [advisor/backend/tests/test_dashboard_ha_health.py](../../advisor/backend/tests/test_dashboard_ha_health.py) — covers T029b: dashboard summary endpoint includes `integrations.home_assistant` block with correct `configured` / `status` / `last_success_at` / `last_error` fields across the five status classes (`ok`, `auth_failure`, `unreachable`, `unexpected_payload`, `not_configured`).

**Checkpoint**: US-1 is complete and independently demo-able. The admin can configure a HA connection, see live entity state in the advisor, see HA-known devices merged into the unified inventory, and see HA connection health surfaced as recommendations + dashboard summary (FR-023/FR-024/FR-025). Run quickstart Steps 1, 2, 4, and 6 to validate.

---

## Phase 4: User Story 2 — Diagnose Thread network health (Priority: P2)

**Goal**: The advisor derives Thread topology from HA (`/api/config/thread/status` + `thread`-integration entities), maintains `thread_border_routers` + `thread_devices`, exposes it via `GET /ha/thread`, renders it in a Thread panel on the HA page, and raises a recommendation via a new rule when a previously-online border router goes offline.

**Independent Test**: Run quickstart Step 3. Requires US-1's poller + connection setup; does not require US-3's notification forwarding.

**Scope maps to**: FR-010, FR-011, FR-012, FR-013, FR-014 · SC-002, SC-006 (partial — chat grounding lands in polish).

### Implementation for User Story 2

- [X] T038 [P] [US2] Extend [advisor/backend/app/services/ha_client.py](../../advisor/backend/app/services/ha_client.py) (from T015) with `async def thread_status()` → `GET /api/config/thread/status`. Tolerate a 404 (→ returns `None`, empty-state handling) or 501 (some HA versions without Thread integration) without raising.
- [X] T039 [US2] Extend [advisor/backend/app/services/ha_poller.py](../../advisor/backend/app/services/ha_poller.py) (from T017) with a `_refresh_thread_tables()` sub-step that calls `ha_client.thread_status()` after `states()`. Parse the diagnostic payload to derive `(border_router_ha_device_id, online, attached_device_count, model)` rows and `(thread_device_ha_device_id, parent_border_router_id, online)` rows. Upsert into `thread_border_routers` / `thread_devices`; on removal, preserve `thread_devices.last_seen_parent_id` (FR-012 surfacing dropped-off devices). When `thread_status()` returns `None`, leave the tables empty — the empty state is legitimate (FR-013).
- [X] T040 [P] [US2] Create [advisor/backend/app/services/rules/thread_border_router_offline.py](../../advisor/backend/app/services/rules/thread_border_router_offline.py) — follows the pattern in existing rules (base class + `evaluate()` returning a list of `RuleResult`). Fires when a `thread_border_routers` row transitioned from `online=true` on the prior cycle to `online=false` on the current cycle. Resolves the HA `device_id` of the border router to its merged `devices.id` (via the `ha_device_id` index — the inventory merge in T018 guarantees every HA border router has a corresponding `devices` row); set `target_type="device"`, `target_id=devices.id`. Matches the pattern used by existing rules (device_offline, pi_cpu_high). If no matching `devices` row exists (should not happen post-merge, but guard for it), skip the cycle and log a warning. Severity `critical`. Auto-resolve when the same row transitions back to `online=true`. Register in [advisor/backend/app/services/rules/__init__.py](../../advisor/backend/app/services/rules/__init__.py).
- [X] T041 [US2] Extend [advisor/backend/app/schemas/home_assistant.py](../../advisor/backend/app/schemas/home_assistant.py) (from T016) with `ThreadBorderRouterOut`, `ThreadDeviceOut`, `ThreadTopologyResponse` per [contracts/home-assistant-api.md](contracts/home-assistant-api.md) §3. Include `orphaned_device_count` (computed as `devices where parent_border_router_id IS NULL`) and `empty_reason` (`"no_thread_integration_data"` when both tables are empty and the connection is `ok`).
- [X] T042 [US2] Extend [advisor/backend/app/routers/home_assistant.py](../../advisor/backend/app/routers/home_assistant.py) (from T020) with `GET /ha/thread` returning `ThreadTopologyResponse`.
- [X] T043 [P] [US2] Create [advisor/frontend/src/components/ThreadTopologyView.tsx](../../advisor/frontend/src/components/ThreadTopologyView.tsx) — renders a card per border router (name, model, online pill, attached device count) and a device list below each card with online-state dots + orphan badge. Shows a dedicated empty-state panel when `empty_reason === "no_thread_integration_data"`.
- [X] T044 [US2] Extend [advisor/frontend/src/pages/HomeAssistant.tsx](../../advisor/frontend/src/pages/HomeAssistant.tsx) (from T026) to mount `<ThreadTopologyView />` as a second tab/section after the entity table, reading `GET /ha/thread` on the same 60 s cadence.
- [X] T045 [P] [US2] Extend [advisor/frontend/src/types.ts](../../advisor/frontend/src/types.ts) (from T023) with `ThreadBorderRouter`, `ThreadDevice`, `ThreadTopologyResponse`.

### Tests for User Story 2 (Test-After)

- [X] T046 [P] [US2] [advisor/backend/tests/test_rule_thread_border_router_offline.py](../../advisor/backend/tests/test_rule_thread_border_router_offline.py) — given a prior cycle where `online=true` and a current cycle where `online=false`, the rule emits exactly one alert with severity `critical`; no alert on consecutive `online=false` cycles (dedup); auto-resolves on transition back to `online=true`.
- [X] T047 [P] [US2] Extend [advisor/backend/tests/test_ha_poller.py](../../advisor/backend/tests/test_ha_poller.py) (from T032) with Thread-table-refresh tests: populated thread_status payload → correct upsert; 404 thread_status → tables cleared; `last_seen_parent_id` preservation when a device drops.
- [X] T048 [P] [US2] Extend [advisor/backend/tests/test_ha_endpoints.py](../../advisor/backend/tests/test_ha_endpoints.py) (from T035) with `GET /ha/thread` tests: happy path, orphaned-device count, empty-state `empty_reason`.
- [X] T049 [P] [US2] [advisor/frontend/src/components/__tests__/ThreadTopologyView.test.tsx](../../advisor/frontend/src/components/__tests__/ThreadTopologyView.test.tsx) — populated topology renders cards and devices; empty state renders the dedicated panel; orphan badge appears only when `parent_border_router_id === null`.

**Checkpoint**: US-2 complete. Quickstart Step 3 validates the Thread view end-to-end including border-router-offline recommendation and empty-state handling.

---

## Phase 5: User Story 3 — Receive advisor alerts as HA push notifications (Priority: P2)

**Goal**: The advisor's existing alert system forwards critical (or higher-threshold, configurable) alerts to Home Assistant via the native `notify.*` service pathway, with a 5-minute exponential-backoff retry budget, delivery state tracked on the alert row, and a terminal-failure recommendation when the budget is exhausted.

**Independent Test**: Run quickstart Step 5. Requires US-1's connection configuration. Does not require US-2.

**Scope maps to**: FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021, FR-022 · SC-003, SC-007.

### Implementation for User Story 3

- [X] T050 [US3] Extend [advisor/backend/app/services/notification_sender.py](../../advisor/backend/app/services/notification_sender.py) with a `type == "home_assistant"` branch. On first attempt (called from the rule engine after alert insert): check mute → `delivery_status="suppressed"` and exit; check severity threshold → if below, `delivery_status="n/a"` and exit; else build the HA notify payload per [research.md](research.md) R7, call `ha_client.call_notify(service=sink.endpoint, payload=payload)`, and on success set `delivery_status="sent"`, `delivery_attempt_count=1`, `delivery_last_attempt_at=now()`, clear `delivery_next_attempt_at`. On 5xx / timeout / `HAUnreachableError`: set `delivery_status="failed"`, increment `delivery_attempt_count`, set `delivery_next_attempt_at` per the backoff table in [research.md](research.md) R6.
- [X] T051 [US3] Create [advisor/backend/app/services/notification_retry_sweeper.py](../../advisor/backend/app/services/notification_retry_sweeper.py) — a small coroutine invoked once per HA poller cycle from `ha_poller.py` (cheapest place to tick). Each sweep: `SELECT * FROM alerts WHERE delivery_status = 'failed' AND delivery_next_attempt_at <= now()`; for each row, re-invoke the HA branch of `notification_sender` (which advances the state machine). When `delivery_attempt_count` would exceed 4 after a failure, instead set `delivery_status="terminal"` and insert a recommendation (reusing the rule-engine's alert-creation helper) with message "Alert #<alert_id> not delivered to Home Assistant after 4 attempts." Keep severity `warning`. Never reopen or retry a `terminal` row.
- [X] T052 [US3] Edit [advisor/backend/app/services/ha_poller.py](../../advisor/backend/app/services/ha_poller.py) (from T017) to call `notification_retry_sweeper.sweep()` at the end of each cycle after the Thread refresh.
- [X] T053 [P] [US3] Extend [advisor/backend/app/services/ha_client.py](../../advisor/backend/app/services/ha_client.py) `call_notify` to return structured success + classify failures consistently with the other methods. Add a helper `async def list_notify_services()` that returns `[s["service"] for s in services() if s["domain"] == "notify"]` for the sink-config UI picker.
- [X] T054 [US3] Extend [advisor/backend/app/routers/settings.py](../../advisor/backend/app/routers/settings.py) (from T021) to accept `type = "home_assistant"` on the existing `POST /settings/notification-sinks` endpoint per [contracts/home-assistant-api.md](contracts/home-assistant-api.md) §4. Add `GET /settings/notification-sinks/available-ha-services` that returns the current HA notify services or 409 when HA is unreachable. **Canonical naming**: store the bare service suffix in `notification_sinks.endpoint` (e.g. `mobile_app_pixel9`), never the dotted full name. The `GET` endpoint strips the `notify.` prefix from HA's `/api/services` response by filtering `domain == "notify"` and emitting only the `service` field. The `ha_client.call_notify(service, payload)` uses the bare suffix in the URL path `/api/services/notify/{service}`.
- [X] T055 [P] [US3] Create [advisor/frontend/src/components/HomeAssistantSinkForm.tsx](../../advisor/frontend/src/components/HomeAssistantSinkForm.tsx) — extends/sits alongside existing `NotificationSinkForm.tsx` (from 011). Dropdown is populated from `GET /settings/notification-sinks/available-ha-services`; falls back to a free-text entry when the dropdown fetch returns 409. Default `min_severity = "critical"` per FR-017.
- [X] T056 [US3] Edit [advisor/frontend/src/pages/Settings.tsx](../../advisor/frontend/src/pages/Settings.tsx) (from T027) to mount `<HomeAssistantSinkForm />` inside the existing Notification Sinks section — add it as an extra `type` option in the add-sink flow.
- [X] T057 [P] [US3] Extend [advisor/frontend/src/pages/Alerts.tsx](../../advisor/frontend/src/pages/Alerts.tsx) with a **Delivery** column showing `delivery_status` (`sent` / `failed (N/4)` / `terminal` / `suppressed` / `n/a` / `pending`) per alert row. The column is tied to the new `alerts` columns from T013 and stays blank for historical pre-feature alerts.

### Tests for User Story 3 (Test-After)

- [X] T058 [P] [US3] [advisor/backend/tests/test_notification_sender_ha.py](../../advisor/backend/tests/test_notification_sender_ha.py) — scenarios: success → `sent`; 5xx 4 times → final attempt flips to `terminal` + recommendation inserted; below-threshold alert → `n/a`; muted alert → `suppressed`; dedup — a second call for the same already-sent alert does not re-POST; **burst coalesce** (FR-022 + SC-007) — simulate 10 separate alert instances for the same `(rule_id, target_id)` firing within 60 s (bypass the rule-engine's own dedup by inserting them directly) and assert exactly one POST is made per distinct `alert_id` with `delivery_status="sent"`, no cross-instance merge POSTs, no silent drops.
- [X] T059 [P] [US3] [advisor/backend/tests/test_notification_retry_sweeper.py](../../advisor/backend/tests/test_notification_retry_sweeper.py) — only `failed` alerts with past-due `delivery_next_attempt_at` are swept; `sent` / `terminal` / `suppressed` / `n/a` are skipped; backoff delays match the R6 table exactly (30 s, 60 s, 120 s, 240 s).
- [X] T060 [P] [US3] Extend [advisor/backend/tests/test_ha_settings_api.py](../../advisor/backend/tests/test_ha_settings_api.py) (from T034) with sink-variant tests: `POST /settings/notification-sinks` with `type="home_assistant"` persists correctly, 400 when no HA connection configured; `GET /settings/notification-sinks/available-ha-services` returns service list when HA OK and 409 when unreachable.
- [X] T061 [P] [US3] [advisor/frontend/src/components/__tests__/HomeAssistantSinkForm.test.tsx](../../advisor/frontend/src/components/__tests__/HomeAssistantSinkForm.test.tsx) — dropdown populated from mock services endpoint; falls back to text entry on 409; default severity is critical; save path calls POST with the expected payload shape.

**Checkpoint**: US-3 complete. Quickstart Step 5 validates successful delivery, retry budget, terminal failure with recommendation, and mute respect.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The remaining cross-story work — AI chat grounding, final doc updates, and the authoritative end-to-end validation.

- [X] T062 [P] Extend [advisor/backend/app/services/prompt_assembler.py](../../advisor/backend/app/services/prompt_assembler.py) per [research.md](research.md) R9: when the chat classifier tags a turn as IoT / Thread / home-automation related, inject a compact HA summary into the prompt (connection health, border-router counts, Thread device counts, up to 20 most-recently-changed entities). Preserve existing grounding for non-IoT turns. Follow the existing pattern used in that file for alerts and device grounding.
- [X] T063 [P] [advisor/backend/tests/test_prompt_assembler_ha.py](../../advisor/backend/tests/test_prompt_assembler_ha.py) — asserts the HA block appears in the prompt for an IoT-tagged turn and is absent from non-IoT turns; asserts the block is bounded at 20 entities.
- [X] T064 [P] Update [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) with the "Home Assistant Integration" subsection per quickstart Step 9: advisor-side config surface, rotation procedure, decommission procedure, the new `ADVISOR_ENCRYPTION_KEY` requirement. This closes the Assumptions statement in [spec.md](spec.md) about the documentation side-effect.
- [X] T065 Run [quickstart.md](quickstart.md) end-to-end on HOLYGRAIL with the real Home Assistant Pi (reference memory: execute quickstart.md as the final validation after every speckit implement). Deploy via `bash scripts/deploy-advisor.sh`. Every "Verify" bullet must pass. If any fails, fix in code and re-run — do **not** edit the quickstart to accommodate unexpected behavior.
- [ ] T066 Merge the feature branch to `master` once T065 passes and all checklist boxes above are complete.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: T006 (migration) depends on T004 (config surface). T007–T013 depend on T006 only through T014 (migration-run verification). T014 is the hard gate before any user story starts.
- **Phase 3 (US-1)**: Depends on Phase 2. Largest single phase; the MVP.
- **Phase 4 (US-2)**: Depends on Phase 2 and on US-1's poller (T017) and HA page shell (T026) existing. Can run in parallel with Phase 5 once US-1 is in.
- **Phase 5 (US-3)**: Depends on Phase 2 and on US-1's connection config (T015, T021). Can run in parallel with Phase 4 once US-1 is in.
- **Phase 6 (Polish)**: Depends on whichever stories are in scope for the release. T062/T063 are strictly informational; T064 must land before T065; T065 gates T066.

### Parallel opportunities

- **Within Phase 2**: T007, T008, T009, T010 are `[P]` (different new files). T011, T012, T013 edit existing models — ideally sequenced to avoid merge churn but each hits a separate file so can run in parallel with care.
- **Within US-1**: All model + schema + service files can be built in parallel once T015 and T017 scaffolding exists. All frontend components (T022, T023, T024, T025) are independent. All US-1 test files (T030–T037) are fully parallel.
- **Across phases 4 and 5**: Both depend on US-1 but are independent of each other; a single developer should pick a lane, a team of two can run them concurrently.

### Parallel example: User Story 1 implementation wave

```text
# Kick off in parallel after T015, T017 scaffolds land:
Task: "T018 ha_inventory_merge.py"
Task: "T020 home_assistant router"
Task: "T021 settings router extensions"

# Frontend wave in parallel:
Task: "T022 homeAssistant.ts service"
Task: "T023 types.ts extensions"
Task: "T024 HAConnectionForm component"
Task: "T025 HAEntityTable component"
```

---

## Implementation Strategy

### MVP first — US-1 alone

1. Phase 1 → Phase 2 → US-1 (T015–T029) → US-1 tests (T030–T037) → run quickstart Steps 1, 2, 4.
2. Feature ships here as "HA entity visibility in the advisor" — no Thread view, no notifications — and already justifies the `ADVISOR_ENCRYPTION_KEY` deploy change.

### Incremental delivery

- After MVP: pick US-2 or US-3 based on which pain is louder (Thread fragmentation diagnosis vs. mobile push). Both are P2 in the spec.
- Polish phase (T062/T063, chat grounding) can ship with either US-2 or US-3; it's additive.

### Parallel team strategy

With two developers after Phase 2:

- Dev A: Phase 3 (US-1) — largest surface, most dependencies.
- Dev B: after Dev A lands T015 + T017 + T021, picks up Phase 4 (US-2) and Phase 5 (US-3) serially, or picks up T062 (AI chat grounding) which is independent.

---

## Notes

- Constitution IV governs test order: every `Tests for User Story N` block follows the implementation for that story. Do **not** reorder.
- No task skips the checklist format — every bullet has `[ ]`, a `T###`, a `[P]` marker where applicable, a `[US#]` label inside story phases, and an explicit file path.
- Reference memory: never `git pull` on HOLYGRAIL — ship via `bash scripts/deploy-advisor.sh` (rsync+SSH).
- Reference memory: run [quickstart.md](quickstart.md) as the final validation after speckit implement — that is T065, not optional.
