# Implementation Plan: Home Assistant Integration

**Branch**: `016-ha-integration` | **Date**: 2026-04-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/Users/jd/Code/camelot/specs/016-ha-integration/spec.md`

## Summary

Teach the Network Advisor to talk to the home's Home Assistant instance over REST: store a single encrypted-at-rest connection (base URL + long-lived access token), poll HA on a configurable interval (default 60 s) for a curated slice of entities, persist the resulting snapshot, and expose it in three places — a new HA dashboard tab showing live IoT device state, a Thread view showing border routers and their attached Thread devices, and the existing AI chat as additional grounding context. Devices HA knows about merge into the unified device inventory using HA's per-device UUID (`device_id`) as the join key, with LAN-present devices deduped against scanner-discovered rows by MAC/IP (requires relaxing `devices.mac_address` to nullable so Thread/Zigbee endpoints can live in the same table). Extend the existing `NotificationSink` model with a `home_assistant` variant that targets a named HA `notify.*` service, routed through the singleton connection's bearer token and base URL. Add one new rule to the rule engine that fires when a previously-online Thread border router goes offline. Delivery retries follow a 5-minute exponential-backoff budget per clarification, and terminal failures produce a recommendation rather than a silent swallow.

Technical approach: follow the established advisor pattern verbatim. A new `services/ha_client.py` wraps HA REST calls with the existing `httpx` dependency. A new `services/ha_poller.py` runs alongside the existing `health_checker.py` and `rule_engine.py` as a third async background loop in `main.py`'s startup, feeding a new `ha_entity_snapshot` table and updating `thread_border_router` / `thread_device` derived rows each cycle. Inventory merge is a small pure function invoked at the end of each poll cycle — MAC/IP match against `devices`, then upsert by `ha_device_id`. Token encryption reuses Python `cryptography`'s `Fernet` with the key supplied via a new `ADVISOR_ENCRYPTION_KEY` env var (same pattern as the existing gluetun-side secret in 015-vpn-sidecar). The existing `notification_sender.py` grows a branch for `type=="home_assistant"` that reads the singleton connection, assembles the HA `/api/services/notify/<service>` POST, and implements the 5-minute exponential-backoff retry schedule as a small local loop (no new queue, no broker). Frontend adds `pages/HomeAssistant.tsx` (entity snapshot + Thread panel), extends `pages/Settings.tsx` with a connection form + sink form, and adds a single column to `pages/Devices.tsx` showing HA provenance and connectivity type.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 (frontend)
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14, `httpx` 0.28 (already in `requirements.txt` — used for HA REST calls and HA `notify` service POST), `cryptography` (new dependency — provides `Fernet` symmetric encryption for the stored access token), Pydantic v2; React 18, Vite 6, Tailwind 3, react-router-dom 7, TanStack React Table 8 (for the entity snapshot table)
**Storage**: PostgreSQL 16 in the existing `advisor_pgdata` Docker volume. Extended via new Alembic migration `008_home_assistant_integration.py` which (a) creates `home_assistant_connections` (singleton, id=1) with encrypted token ciphertext, (b) creates `ha_entity_snapshots` keyed by `(ha_device_id, entity_id)`, (c) creates `thread_border_routers` and `thread_devices` (derived, refreshed each poll), (d) adds `ha_device_id`, `ha_connectivity_type`, `ha_last_seen` columns to `devices`, (e) relaxes `devices.mac_address` from `NOT NULL UNIQUE` to `NULL` with a partial unique index on non-null values, (f) adds `home_assistant_id` FK column to `notification_sinks` to link sink rows to the connection they target, (g) adds `delivery_last_attempt_at`, `delivery_next_attempt_at`, `delivery_attempt_count`, `delivery_status` columns to `alerts` (so the retry-budget state lives on the alert row itself — no new delivery-log table per constitution II simplicity)
**Testing**: pytest + pytest-asyncio + httpx AsyncClient (backend, existing pattern under `advisor/backend/tests/`); Vitest + @testing-library/react (frontend, existing pattern under `advisor/frontend/src/components/__tests__/`). Home Assistant REST is mocked at the `httpx.AsyncClient` boundary; no live HA instance required for the unit layer
**Target Platform**: Docker Compose stack on HOLYGRAIL (Ubuntu 24.04, x86_64). Backend and frontend already containerized under `advisor/docker-compose.yml`. Home Assistant is reachable at a user-supplied LAN URL (placeholder: `http://homeassistant.local:8123` or the Pi's IP). No new containers
**Project Type**: Web application (backend + frontend monorepo under `advisor/`)
**Performance Goals**: Poll cycle completes in under 2 s for the home-scale entity set (≤200 filtered entities) (supports SC-001, SC-002). HA snapshot endpoint returns in under 500 ms. Notification forwarding retry budget 5 min exponential backoff (~4 attempts at 30 s / 60 s / 120 s / 240 s per clarification Q3) with terminal-failure recommendation. Dashboard updates within one poll cycle (SC-001)
**Constraints**: Local-only — HA is on the LAN (Constitution I). Access token symmetric-encrypted at rest (clarification Q2); encryption key via `ADVISOR_ENCRYPTION_KEY` env var; MUST NOT be committed and MUST NOT appear in logs or in any browser-destined payload (FR-003). HA outage MUST NOT crash the advisor or its dashboards (FR-023, SC-004). No OAuth2 flow, no multi-instance HA support, no polling via WebSocket in v1 (Assumptions). Only one HA connection ever (FR-001). Rebuilt HA instances trigger fresh reconciliation, not a guess-based mapping (FR-030)
**Scale/Scope**: Single HA instance, ≤200 filtered entities after domain filter, typically 2-5 Thread border routers and 20-40 Thread/Zigbee endpoints in this home. One new background loop, one new HA client, one new rule, one new migration, one new frontend page, one extended Settings page, one extended notification-sender path

### Decisions deferred to planning, now resolved (see research.md)

- **HA API style**: REST polling on a configurable interval. WebSocket subscription is a future enhancement (per spec Assumptions); simpler to start and lines up with clarification Q3's retry model. See research R1.
- **Entity-domain filter**: curated built-in list of `device_tracker`, `binary_sensor`, `sensor` (diagnostic device-class only), `switch`, `update`, and anything emitted by HA's `thread` integration. See research R2.
- **Thread topology source**: HA's `thread` integration exposes border routers as `device_tracker` entities and a diagnostic JSON blob at `/api/config/thread/status`. Use both — the diagnostic blob gives the device→border-router parentage that entity state alone doesn't. See research R3.
- **Token encryption**: `cryptography.fernet.Fernet` with a 32-byte URL-safe key from the `ADVISOR_ENCRYPTION_KEY` env var. Fernet is versioned AES-128-CBC + HMAC — simpler than rolling a KMS equivalent on the LAN. See research R4.
- **Mac-nullable migration strategy**: keep `mac_address` as text (not a new column), drop the `NOT NULL UNIQUE` constraint, add a partial unique index `WHERE mac_address IS NOT NULL`. Existing rows are unaffected. See research R5.
- **Retry budget realization**: state machine held on the `alerts` row itself (columns in (g) above). The background loop sweeps for rows whose `delivery_next_attempt_at <= now()` each poll cycle. No new Celery, no RQ, no Redis. See research R6.

## Constitution Check

Evaluated against `.specify/memory/constitution.md` v1.1.0.

| Principle | Assessment |
| --- | --- |
| **I. Local-First** | PASS. The only external system is Home Assistant, which is a LAN-resident service on a dedicated Pi. No cloud APIs, no telemetry, no third-party auth. The access token is issued by the home's own HA instance. |
| **II. Simplicity & Pragmatism** | PASS. Feature rides the existing advisor monorepo — one new background loop (following the `health_checker.py` / `rule_engine.py` pattern), one new rule (matching the existing six in `services/rules/`), one new migration, one new HA client module. Delivery retry state lives on the `alerts` row (no new delivery-log table, no Redis, no queue). The notification-sender gets a `type=="home_assistant"` branch inside the existing function rather than a new sender abstraction. No DSL, no plug-in system, no multi-tenant anything. |
| **III. Containerized Everything** | PASS. No new containers. Backend additions go into the existing `advisor` container; frontend into the existing `advisor-ui` container. Home Assistant itself is out-of-scope to host — it's an existing external service on the LAN. The new `ADVISOR_ENCRYPTION_KEY` env var is injected via the existing `.env` pathway (gitignored). |
| **IV. Test-After (Not Test-First)** | PASS. Implementation ships first; tests follow using the existing pytest + Vitest harnesses. `/speckit.tasks` will order implementation-before-tests per the constitution. HA mocking happens at the `httpx.AsyncClient` boundary so tests exercise real code paths inside the advisor. |
| **V. Observability** | PASS. The HA poller emits structured JSON log lines each cycle (entities pulled, delta vs prior, dedup hits, duration). HA connection health is surfaced in the service registry (FR-025) so the existing `/health` / dashboard mechanisms flag degradation. Failed notification deliveries raise a recommendation per FR-020 instead of silently vanishing. The AI chat grounding (FR-009) extends the existing `prompt_assembler.py` which already satisfies the constitution's AI-enhanced-monitoring expectation — HA is another grounding data source. |

**Result**: No violations. Proceeding with Phase 0 research.

## Project Structure

### Documentation (this feature)

```text
specs/016-ha-integration/
├── plan.md                       # This file
├── spec.md                       # Feature spec (written, clarified)
├── research.md                   # Phase 0 output
├── data-model.md                 # Phase 1 output
├── quickstart.md                 # Phase 1 output
├── contracts/
│   └── home-assistant-api.md     # REST contract for /settings/home-assistant, /ha/entities, /ha/thread, extension to /settings/notification-sinks
└── checklists/
    └── requirements.md           # Spec quality checklist (already exists)
```

### Source Code (repository root)

```text
advisor/
├── backend/
│   ├── app/
│   │   ├── main.py                                # EDIT: start ha_poller alongside health_checker + rule_engine
│   │   ├── config.py                              # EDIT: add ADVISOR_ENCRYPTION_KEY, HA poll interval
│   │   ├── security.py                            # NEW: Fernet wrapper (encrypt/decrypt_token) sourcing key from env
│   │   ├── models/
│   │   │   ├── home_assistant_connection.py       # NEW: singleton connection row (base_url, token_ciphertext, last_success, last_error)
│   │   │   ├── ha_entity_snapshot.py              # NEW: per-entity snapshot rows
│   │   │   ├── thread_border_router.py            # NEW: derived border-router row
│   │   │   ├── thread_device.py                   # NEW: derived Thread-device row
│   │   │   ├── device.py                          # EDIT: ha_device_id, ha_connectivity_type, ha_last_seen; mac_address nullable
│   │   │   ├── notification_sink.py               # EDIT: home_assistant_id FK + type="home_assistant" documented
│   │   │   └── alert.py                           # EDIT: delivery_status, delivery_attempt_count, delivery_last_attempt_at, delivery_next_attempt_at
│   │   ├── routers/
│   │   │   ├── home_assistant.py                  # NEW: /ha/entities, /ha/thread GET endpoints for dashboard
│   │   │   └── settings.py                        # EDIT: /settings/home-assistant GET/PUT/DELETE + test-connection; extend notification-sinks to accept type="home_assistant"
│   │   ├── services/
│   │   │   ├── ha_client.py                       # NEW: httpx wrapper around HA REST — states(), config(), thread_status(), notify(service, payload)
│   │   │   ├── ha_poller.py                       # NEW: background async loop — fetches states + thread status, upserts snapshots, refreshes derived Thread tables, runs inventory merge, updates connection health
│   │   │   ├── ha_inventory_merge.py              # NEW: pure-function merge — HA devices into `devices` table by MAC/IP match or ha_device_id upsert
│   │   │   ├── notification_sender.py             # EDIT: add home_assistant branch that POSTs /api/services/notify/<service> through the singleton connection; implement 5-min exponential-backoff retry loop driving alerts.delivery_* columns
│   │   │   ├── prompt_assembler.py                # EDIT: include HA entity snapshot + Thread topology summary in chat grounding (FR-009)
│   │   │   └── rules/
│   │   │       └── thread_border_router_offline.py   # NEW: rule fires when a previously-online Thread border router transitions to offline (FR-014)
│   │   └── schemas/                               # EDIT: pydantic schemas for HA connection, HA entity, Thread views, notification-sink HA variant
│   ├── migrations/versions/
│   │   └── 008_home_assistant_integration.py      # NEW: per Storage spec above
│   └── tests/
│       ├── test_ha_client.py                      # NEW: httpx mock — 200s, 401, 5xx, timeout, malformed payload
│       ├── test_ha_poller.py                      # NEW: snapshot upsert, derived-table refresh, stale-connection handling
│       ├── test_ha_inventory_merge.py             # NEW: LAN-match dedup, new Thread row, HA-reinstall reconciliation
│       ├── test_ha_settings_api.py                # NEW: PUT/DELETE + test-connection + token redaction
│       ├── test_ha_endpoints.py                   # NEW: /ha/entities, /ha/thread shape + empty-state
│       ├── test_notification_sender_ha.py         # NEW: success path, 5xx→retry, final-failure recommendation, mute respect, dedup
│       ├── test_rule_thread_border_router_offline.py  # NEW
│       └── test_security_fernet.py                # NEW: encrypt/decrypt round-trip, missing-key failure mode
└── frontend/
    └── src/
        ├── App.tsx                                # EDIT: add /home-assistant route; nav link
        ├── pages/
        │   ├── HomeAssistant.tsx                  # NEW: entity snapshot table + Thread panel (border routers + devices)
        │   ├── Settings.tsx                       # EDIT: mount HAConnectionForm + HomeAssistantSinkForm
        │   └── Devices.tsx                        # EDIT: add "HA" column (connectivity type, HA provenance badge)
        ├── components/
        │   ├── HAConnectionForm.tsx               # NEW: base URL + token input, Test Connection control, redacted read-back of saved token
        │   ├── HAEntityTable.tsx                  # NEW: TanStack Table of entity snapshots with domain filter + last-changed sort
        │   ├── ThreadTopologyView.tsx             # NEW: border-router cards with device counts + orphaned-device indicator
        │   ├── HomeAssistantSinkForm.tsx          # NEW: choose a HA notify service + severity threshold
        │   └── __tests__/
        │       ├── HAConnectionForm.test.tsx
        │       ├── HAEntityTable.test.tsx
        │       └── ThreadTopologyView.test.tsx
        ├── services/
        │   └── homeAssistant.ts                   # NEW: fetch wrapper for /settings/home-assistant, /ha/entities, /ha/thread
        └── types.ts                               # EDIT: add HAConnection, HAEntity, ThreadBorderRouter, ThreadDevice, HomeAssistantSink types
```

**Structure Decision**: Feature slots into the existing `advisor/` monorepo without introducing a new top-level directory. Backend adds one new router, one new client, one new poller, one new rule, one new migration, and five new models — all following conventions established in F4.2 → F4.5. Frontend adds one new page and four components under the existing `pages/` / `components/` / `services/` layout. No new Compose stacks, no new containers, no new languages. The only new runtime dependency is `cryptography` (for Fernet), pinned in `requirements.txt`.

## Complexity Tracking

No constitution violations require justification. Table intentionally empty.
