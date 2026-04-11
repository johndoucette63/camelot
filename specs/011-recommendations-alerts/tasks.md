---
description: "Task list for feature 011-recommendations-alerts"
---

# Tasks: Recommendations & Alerts

**Input**: Design documents from `/Users/jd/Code/camelot/specs/011-recommendations-alerts/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/alerts-api.md, quickstart.md
**Tests**: REQUIRED by constitution (Principle IV: Test-After). Tests are written AFTER the code they validate, within the same story phase, using the existing pytest and Vitest harnesses.

**Organization**: Tasks are grouped by the five user stories from spec.md (US1–US5) so each slice can be implemented, tested, and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in the same phase)
- **[Story]**: Which user story the task belongs to (US1, US2, US3, US4, US5)
- Setup and Polish phases have no story label

## Path Conventions

Feature slots into the existing `advisor/` monorepo:

- Backend: `advisor/backend/app/` and `advisor/backend/tests/`
- Frontend: `advisor/frontend/src/`
- Migrations: `advisor/backend/migrations/versions/`

All paths below are absolute from repo root (`/Users/jd/Code/camelot`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Schema, models, and frontend type definitions shared by every user story. No business logic yet.

- [X] T001 Create Alembic migration `advisor/backend/migrations/versions/004_recommendations_alerts.py` that (a) drops the `acknowledged` column from `alerts`, (b) adds columns `rule_id VARCHAR(100) NOT NULL`, `target_type VARCHAR(20) NOT NULL`, `target_id INTEGER NULL`, `state VARCHAR(20) NOT NULL DEFAULT 'active'`, `acknowledged_at TIMESTAMP NULL`, `resolved_at TIMESTAMP NULL`, `resolution_source VARCHAR(10) NULL`, `source VARCHAR(10) NOT NULL DEFAULT 'rule'`, `suppressed BOOLEAN NOT NULL DEFAULT false`, (c) creates partial unique index `alerts_active_rule_target_uidx` on `(rule_id, target_type, target_id) WHERE state != 'resolved' AND suppressed = false`, (d) creates index `alerts_state_created_at_idx` on `(state, created_at DESC)`, (e) creates index `alerts_rule_target_resolved_at_idx` on `(rule_id, target_type, target_id, resolved_at DESC)`, (f) creates tables `alert_thresholds`, `rule_mutes`, `notification_sinks` per data-model.md §1.2–1.4, (g) seeds `alert_thresholds` with the default rows listed in data-model.md §1.2 (`cpu_percent`, `disk_percent`, `service_down_minutes`, `device_offline_minutes`).
- [X] T002 Update the existing `advisor/backend/app/models/alert.py`: drop the `acknowledged` field; add `rule_id`, `target_type`, `target_id`, `state`, `acknowledged_at`, `resolved_at`, `resolution_source`, `source`, `suppressed` as `Mapped[...]` / `mapped_column()` fields matching the migration; keep the existing `device` and `service` relationships intact.
- [X] T003 [P] Create `advisor/backend/app/models/alert_threshold.py` with an `AlertThreshold` SQLAlchemy model mapping to `alert_thresholds` (fields per data-model.md §1.2).
- [X] T004 [P] Create `advisor/backend/app/models/rule_mute.py` with a `RuleMute` SQLAlchemy model mapping to `rule_mutes` (fields per data-model.md §1.3).
- [X] T005 [P] Create `advisor/backend/app/models/notification_sink.py` with a `NotificationSink` SQLAlchemy model mapping to `notification_sinks` (fields per data-model.md §1.4).
- [X] T006 [P] Update `advisor/backend/app/config.py` to add `RULE_ENGINE_INTERVAL_SECONDS` (default 60), `AI_NARRATIVE_TIMEOUT_SECONDS` (default 10), `AI_NARRATIVE_CACHE_SECONDS` (default 60), and `HA_WEBHOOK_TIMEOUT_SECONDS` (default 5) as environment-overridable settings.
- [X] T007 [P] Update `advisor/frontend/src/types.ts` to add TypeScript types `Alert`, `AlertState`, `AlertSeverity`, `AlertListResponse`, `Recommendation`, `RecommendationsResponse`, `AiNarrative`, `Threshold`, `RuleMute`, `NotificationSink` matching the contract in `contracts/alerts-api.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The rule engine skeleton + base rule abstraction + route shells. No user story can start until this phase compiles and the engine loop starts cleanly on backend boot.

**CRITICAL**: Nothing in Phase 3+ can begin until this phase is complete.

- [X] T008 Create `advisor/backend/app/services/rules/__init__.py` with an empty `RULES: list[Rule] = []` registry. Individual rules will append to this list in US1.
- [X] T009 Create `advisor/backend/app/services/rules/base.py` defining `Severity`, `TargetType` literals, the `RuleResult` dataclass, the `RuleContext` dataclass (per data-model.md §2.2), and the `Rule` base class with `id`, `name`, `severity`, `sustained_window`, and an abstract `async evaluate(ctx)` method (per data-model.md §2.1).
- [X] T010 Create `advisor/backend/app/services/rule_engine.py` implementing the cycle loop per data-model.md §4: build `RuleContext`, iterate `RULES`, apply the in-process sustained-window streak map, apply the DB-backed 10-minute cool-down filter, apply mute check (stub — returns "not muted" for now, filled in US2), `INSERT ... ON CONFLICT DO NOTHING` via the unique partial index, auto-resolve open alerts whose condition cleared, call the notification hook (stub — no-op until US5), prune alerts older than 30 days, log `rule_engine.cycle.completed` JSON line with durations and counters. Wrap each cycle in `try/except Exception`. Sleep `RULE_ENGINE_INTERVAL_SECONDS` between cycles. Follow the exact pattern already used by `advisor/backend/app/services/health_checker.py`.
- [X] T011 Update `advisor/backend/app/main.py`: on app startup, `asyncio.create_task(rule_engine.run(app))` alongside the existing `fetch_containers` and `run_health_checks` background tasks; on shutdown, cancel the task.
- [X] T012 [P] Create empty router shells `advisor/backend/app/routers/recommendations.py`, `advisor/backend/app/routers/alerts.py`, and `advisor/backend/app/routers/settings.py`, each exporting an `APIRouter` with the correct path prefix. Register all three in `advisor/backend/app/main.py`.
- [X] T013 [P] Update `advisor/frontend/src/App.tsx` to add `/alerts` and `/settings` routes pointing to placeholder `Alerts.tsx` and `Settings.tsx` page components (render a single `<h1>` heading for now). Add nav links for both next to the existing entries.
- [X] T014 [P] Create `advisor/frontend/src/pages/Alerts.tsx` placeholder (h1 only, no logic yet).
- [X] T015 [P] Create `advisor/frontend/src/pages/Settings.tsx` placeholder (h1 only, no logic yet).

**Checkpoint**: Running `docker compose up` should start the advisor backend with the rule engine loop emitting `rule_engine.cycle.completed` log lines every 60 seconds (with `rules_evaluated: 0`), and the frontend should show empty `/alerts` and `/settings` pages. User story work can now begin in parallel.

---

## Phase 3: User Story 1 — Proactive rule-based recommendations (Priority: P1) 🎯 MVP

**Goal**: The advisor proactively tells the admin about problems and optimizations. Five rules ship — high Pi CPU, high disk, service down, Ollama unavailable, unknown device — each creates alert instances with lifecycle `active → resolved`, dedup via `(rule_id, target_id)`, 5-minute sustained-breach window, 10-minute cool-down. The dashboard shows a recommendations panel. No AI narrative yet, no HA forwarding yet, no manual ack/resolve yet — just the core rule-driven pipeline.

**Independent Test**: Drive torrentbox CPU to >80% for 6 minutes; a `pi_cpu_high` entry appears at `GET /recommendations` and on the dashboard panel. Stop the burner; the alert auto-resolves on the next cycle. Re-trigger within 10 minutes; no new entry is created (cool-down). Running each of the other four rules through an equivalent forced condition (per quickstart.md §1b–1e) produces the same shape.

### Implementation for User Story 1

- [X] T016 [P] [US1] Create `advisor/backend/app/services/rules/pi_cpu_high.py` defining `PiCpuHighRule(Rule)` with `id='pi_cpu_high'`, `severity='warning'`, `sustained_window=timedelta(minutes=5)`. `evaluate()` reads `ctx.thresholds['cpu_percent']` and the latest CPU metric per device (Pi devices only — filter by device role), returning one `RuleResult(target_type='device', target_id=<id>, message=...)` per breaching Pi.
- [X] T017 [P] [US1] Create `advisor/backend/app/services/rules/disk_high.py` defining `DiskHighRule(Rule)` with `id='disk_high'`, `severity='warning'`, `sustained_window=timedelta(0)` (fire on first observation — disks don't flap). `evaluate()` iterates devices, reads the latest disk metric, returns one `RuleResult` per device above `ctx.thresholds['disk_percent']`.
- [X] T018 [P] [US1] Create `advisor/backend/app/services/rules/service_down.py` defining `ServiceDownRule(Rule)` with `id='service_down'`, `severity='critical'`, `sustained_window=timedelta(0)` (sustained logic is baked into the rule itself — uses `ctx.thresholds['service_down_minutes']`). `evaluate()` iterates `ctx.services`, checks `ctx.health_results[service.id]`, and returns a `RuleResult(target_type='service', target_id=service.id, ...)` for each service whose latest `status='down'` has persisted for ≥ threshold minutes.
- [X] T019 [P] [US1] Create `advisor/backend/app/services/rules/ollama_unavailable.py` defining `OllamaUnavailableRule(Rule)` with `id='ollama_unavailable'`, `severity='info'`, `sustained_window=timedelta(0)`. `evaluate()` returns a single `RuleResult(target_type='system', target_id=None, ...)` iff `ctx.ollama_healthy is False`.
- [X] T020 [P] [US1] Create `advisor/backend/app/services/rules/unknown_device.py` defining `UnknownDeviceRule(Rule)` with `id='unknown_device'`, `severity='warning'`. `evaluate()` computes "seen in ≥3 consecutive scans spanning ≥30 minutes and not in known inventory" from `ctx.recent_scans`, returning one `RuleResult(target_type='system', target_id=None, message=f"Unknown device {mac} seen on LAN")` per persistent unknown MAC. Per data-model.md §2.4, encode the MAC as a suffix on the rule_id (`unknown_device:aa:bb:cc:dd:ee:ff`) so dedup works per MAC.
- [X] T020a [P] [US1] Create `advisor/backend/app/services/rules/device_offline.py` defining `DeviceOfflineRule(Rule)` with `id='device_offline'`, `severity='warning'`, `sustained_window=timedelta(0)` (the threshold itself is the grace period). `evaluate()` reads `ctx.thresholds['device_offline_minutes']`, iterates `ctx.devices`, and returns a `RuleResult(target_type='device', target_id=<id>, message=...)` for any device whose most recent metric timestamp is older than `now - threshold_minutes` AND that has at least one prior metric on record (never-seen devices are skipped to avoid false positives on the first scan after deploy). Satisfies FR-006 "raise appropriate alerts for missing-data conditions".
- [X] T021 [US1] Edit `advisor/backend/app/services/rules/__init__.py` to import and instantiate all six rules into the `RULES` list. Must run after T016–T020a.
- [X] T022 [US1] Extend `advisor/backend/app/services/rule_engine.py` to build the full `RuleContext` in the cycle loop: load devices, services, latest health results, container state, materialize thresholds from the DB, probe Ollama with a 1-second `httpx.get` to set `ollama_healthy`, and load the last 6 scans for the `UnknownDeviceRule`. Ensure `ctx` is passed to every rule's `evaluate()`.
- [X] T023 [US1] Fill in the recommendations router at `advisor/backend/app/routers/recommendations.py`: `GET /recommendations` returns `{active, counts, ai_narrative: null}` per `contracts/alerts-api.md §1`. Active list is `SELECT ... FROM alerts WHERE state IN ('active','acknowledged') AND suppressed = false ORDER BY severity DESC, created_at DESC`. Join to devices and services for `target_label`. The `ai_narrative` field is stubbed as `null` — US4 fills it in.
- [X] T024 [US1] Create `advisor/frontend/src/services/recommendations.ts` exporting `fetchRecommendations(): Promise<RecommendationsResponse>` as a typed wrapper around `fetch('/api/recommendations')`.
- [X] T025 [US1] Create `advisor/frontend/src/components/RecommendationsPanel.tsx` — a React component that polls `/api/recommendations` every 30 seconds, renders the active list grouped by severity with severity-colored badges, shows the severity counts, and shows an empty-state message when no alerts are active. The `ai_narrative` banner is wired up as a no-op for now (US4 fills in rendering).
- [X] T026 [US1] Mount `<RecommendationsPanel />` on the existing `advisor/frontend/src/pages/Home.tsx` dashboard so recommendations appear at the top of the home view.

### Tests for User Story 1 (written after implementation, per constitution IV)

- [X] T027 [P] [US1] Create `advisor/backend/tests/test_rules_catalog.py` with one pytest test per shipped rule (six total), each feeding a synthetic `RuleContext` (hand-built in-memory) and asserting the `evaluate()` return matches the expected `RuleResult` list. Cover both "breaching" and "not breaching" branches for each rule. For `device_offline`, additionally assert that never-seen devices (no prior metric on record) do NOT trigger the rule even when their last-seen timestamp is null or old.
- [X] T028 [P] [US1] Create `advisor/backend/tests/test_rule_engine.py` covering: (a) a full cycle creates one active alert per `RuleResult`, (b) a second cycle with the same condition does NOT create duplicates (partial unique index), (c) clearing the condition auto-resolves the alert, (d) re-firing within the 10-minute cool-down window does NOT create a new instance, (e) re-firing after the cool-down DOES create a new instance, (f) sustained-window streak map drops short spikes, (g) 30-day retention pruning removes old `resolved` rows. Uses pytest-asyncio and the existing test DB fixture.
- [X] T029 [P] [US1] Create `advisor/backend/tests/test_recommendations_api.py` covering: (a) empty response shape when no alerts active, (b) populated response shape with severity ordering correct, (c) `counts` matches `active` length by severity, (d) suppressed alerts excluded from `active`, (e) `ai_narrative` is `null` in v1.
- [X] T030 [P] [US1] Create `advisor/frontend/src/components/__tests__/RecommendationsPanel.test.tsx` using Vitest + @testing-library/react: empty state, populated state with severity badges, severity counts rendered correctly, mocks `fetchRecommendations` via `vi.mock`.

**Checkpoint**: User Story 1 fully functional. The MVP ships here. Run quickstart.md §0–1 to validate.

---

## Phase 4: User Story 2 — Configurable thresholds + noise control (Priority: P2)

**Goal**: Admin can change alert thresholds from the settings UI without a service restart, and can mute a specific `(rule, target)` pair for a TTL to suppress noise without raising global thresholds.

**Independent Test**: Open `/settings`, lower the CPU threshold to 5%, save, and observe that CPU alerts fire against all Pis on the next cycle (≤5 min sustained + 60 s cycle). Restore the default. Create a mute for `pi_cpu_high` on torrentbox for 1 hour; re-trigger the CPU condition and confirm (a) no active alert appears in `/recommendations`, (b) the alert log shows a `suppressed=true` row, (c) cancelling the mute via `DELETE /settings/mutes/{id}` resumes normal behavior.

### Implementation for User Story 2

- [X] T031 [US2] Fill in threshold endpoints in `advisor/backend/app/routers/settings.py`: `GET /settings/thresholds` returns all rows; `PUT /settings/thresholds/{key}` validates `value` against `[min_value, max_value]` and 404s on unknown key. Per contracts/alerts-api.md §3.
- [X] T032 [US2] Extend `advisor/backend/app/routers/settings.py` with mute endpoints: `GET /settings/mutes` (with `include_expired` query param), `POST /settings/mutes` (duration ≤ 7 days, validates target match), `DELETE /settings/mutes/{id}` (idempotent cancel). Per contracts/alerts-api.md §4.
- [X] T033 [US2] Update `advisor/backend/app/services/rule_engine.py` mute-check step from the T010 stub to real enforcement: for each `RuleResult` before insertion, query `rule_mutes WHERE rule_id = ... AND target_type = ... AND target_id = ... AND cancelled_at IS NULL AND expires_at > now()`. On match, INSERT the alert with `suppressed=true` and skip downstream notification hooks. Increment the `alerts_suppressed` counter in the cycle log.
- [X] T034 [P] [US2] Create `advisor/frontend/src/services/settings.ts` exporting `fetchThresholds`, `updateThreshold`, `fetchMutes`, `createMute`, `cancelMute` — typed wrappers around the settings endpoints.
- [X] T035 [P] [US2] Create `advisor/frontend/src/components/ThresholdForm.tsx` — renders each threshold as an editable numeric input with unit, default value display, inline validation against `min_value`/`max_value`, and a save button per row. Shows the API's 400 error message on validation failure.
- [X] T036 [P] [US2] Create `advisor/frontend/src/components/MuteList.tsx` — renders active mutes with rule name, target label, remaining TTL (live countdown), cancel button. Includes a "New mute" dialog for selecting rule + target + duration + optional note.
- [X] T037 [US2] Replace the placeholder content of `advisor/frontend/src/pages/Settings.tsx` with `<ThresholdForm />` and `<MuteList />` sections (stacked). Notification sink section is left as an empty placeholder for US5.

### Tests for User Story 2

- [X] T038 [P] [US2] Create `advisor/backend/tests/test_settings_thresholds_api.py`: list returns all seeded rows, PUT updates a value, PUT with out-of-range value returns 400, PUT on unknown key returns 404, updated value is persisted and visible in a subsequent GET.
- [X] T039 [P] [US2] Create `advisor/backend/tests/test_settings_mutes_api.py`: create/list/delete cycle, duration > 7 days is rejected, system-target mutes reject `target_id`, double-delete is idempotent, `include_expired=false` hides cancelled and expired rows.
- [X] T040 [P] [US2] Extend `advisor/backend/tests/test_rule_engine.py` with a "mute suppression" test: create a mute for `(rule_id, target_type, target_id)`, trigger the rule, assert the row exists with `suppressed=true` AND is excluded from `/recommendations`.
- [X] T041 [P] [US2] Create `advisor/frontend/src/components/__tests__/ThresholdForm.test.tsx`: renders thresholds, rejects invalid input before calling the API, shows API error on 400, successful save re-renders new value.
- [X] T042 [P] [US2] Create `advisor/frontend/src/components/__tests__/MuteList.test.tsx`: renders active mutes, countdown updates, cancel button calls the service.

**Checkpoint**: User Story 2 fully functional. Run quickstart.md §2, §4.

---

## Phase 5: User Story 3 — Alert history log (Priority: P2)

**Goal**: Admin can browse a searchable log of all past alerts and recommendations with severity/device/date filters, and can manually acknowledge or resolve active alerts.

**Independent Test**: Trigger and resolve a known sequence of alerts, navigate to `/alerts`, confirm each entry appears with correct metadata; apply severity and device filters and confirm the result set narrows correctly; acknowledge an active alert via the row action and confirm state persists across reload; manually resolve it and confirm `resolution_source='manual'`.

### Implementation for User Story 3

- [X] T043 [US3] Fill in `advisor/backend/app/routers/alerts.py`: `GET /alerts` with filters (`severity`, `state`, `rule_id`, `device_id`, `service_id`, `since`, `until`, `include_suppressed`, `limit`, `offset`), clamping `since` to 30 days ago. `rule_id` matches either exactly (e.g. `pi_cpu_high`) or as a prefix-before-`:` (e.g. `rule_id=unknown_device` matches all `unknown_device:*` rows) so the caller does not need to know the per-MAC encoding. Returns `{total, items, limit, offset}` per contracts/alerts-api.md §2. Uses the `alerts_state_created_at_idx` index.
- [X] T044 [US3] Add `POST /alerts/{id}/acknowledge` to `advisor/backend/app/routers/alerts.py`: transitions `active → acknowledged`, idempotent on already-acknowledged, 404 on not found, 409 on resolved. Sets `acknowledged_at = now()`.
- [X] T045 [US3] Add `POST /alerts/{id}/resolve` to `advisor/backend/app/routers/alerts.py`: transitions to `resolved` with `resolution_source='manual'`, 404/409 as above.
- [X] T046 [P] [US3] Create `advisor/frontend/src/services/alerts.ts` exporting `fetchAlerts(filters)`, `acknowledgeAlert(id)`, `resolveAlert(id)` — typed wrappers.
- [X] T047 [P] [US3] Create `advisor/frontend/src/components/AlertRow.tsx` — one row in the alert history table, renders severity badge, target label, message (truncated), state, timestamps, and conditional ack/resolve buttons based on state.
- [X] T048 [US3] Replace the placeholder content of `advisor/frontend/src/pages/Alerts.tsx` with a TanStack React Table rendering `AlertRow` rows, filter controls (severity multi-select, device dropdown, date-range picker, `include_suppressed` toggle), pagination, and empty-state message.

### Tests for User Story 3

- [X] T049 [P] [US3] Create `advisor/backend/tests/test_alerts_api.py`: list with no filters returns all within 30 days, severity/state/device/rule_id filter combinations return correct subsets, `rule_id=unknown_device` matches `unknown_device:aa:bb:...` rows via prefix match, `rule_id=pi_cpu_high` only matches exact, `since`/`until` bounds respected, `include_suppressed` toggle works, pagination correct, ack endpoint transitions state + sets `acknowledged_at`, ack on resolved returns 409, resolve endpoint transitions state + sets `resolved_at` + `resolution_source='manual'`, resolve on already-resolved returns 409, 404 on unknown id.
- [X] T050 [P] [US3] Create `advisor/frontend/src/components/__tests__/AlertRow.test.tsx`: renders all states correctly, ack/resolve buttons shown only for appropriate states, button clicks call the right service method.

**Checkpoint**: User Story 3 fully functional. Run quickstart.md §3.

---

## Phase 6: User Story 4 — AI-assisted narrative (Priority: P3)

**Goal**: When Ollama is healthy, the dashboard shows a consolidated narrative that summarizes co-firing alerts and explains anomalies. When Ollama is slow or unreachable, the narrative is gracefully omitted and rule-based alerts still display normally.

**Independent Test**: Trigger two correlated alerts simultaneously (CPU + disk on torrentbox), confirm `GET /recommendations` returns a non-null `ai_narrative.text` that references both, rendered in the panel with an AI-assisted badge. Stop Ollama and confirm `ai_narrative` is null and the active list still renders.

### Implementation for User Story 4

- [X] T051 [US4] Create `advisor/backend/app/services/ai_narrative.py` exposing `async def get_narrative(active_alerts: list[Alert]) -> dict | None`. Internal TTL cache keyed by `tuple(sorted(a.id for a in active_alerts))` with `AI_NARRATIVE_CACHE_SECONDS` expiry. On cache miss, build the prompt per research.md §4, call `ollama_client.generate(...)` with `AI_NARRATIVE_TIMEOUT_SECONDS` total budget, return `{"text": ..., "generated_at": ..., "source": "ollama"}`. On timeout, connection error, or empty response, return `None` and log `ai_narrative.call.failed`.
- [X] T052 [US4] Update `advisor/backend/app/routers/recommendations.py` `GET /recommendations`: after building the `active` list, call `ai_narrative.get_narrative(active)` and include the result in the response under `ai_narrative`. If `None`, serialize as `null`.
- [X] T053 [US4] Update `advisor/frontend/src/components/RecommendationsPanel.tsx`: when `ai_narrative` is non-null, render it as a distinct banner above the alert list with an "AI-assisted" badge, using a different background color / icon than rule-based alerts (FR-019). When null, hide the banner entirely.

### Tests for User Story 4

- [X] T054 [P] [US4] Create `advisor/backend/tests/test_ai_narrative.py`: (a) happy path returns a dict with `text`, (b) cache hit path does not re-call Ollama, (c) Ollama timeout returns `None` and logs the error, (d) Ollama connection refused returns `None`, (e) different active alert ID sets produce different cache keys, (f) **anti-fabrication structural assertion**: the prompt built by `ai_narrative.build_prompt(active_alerts)` contains explicit instructions forbidding invented alerts (string-match for phrases like "do not invent" / "only reference alerts provided" / "must not add alerts") — satisfies FR-021 at the prompt construction layer without needing live LLM output, (g) the prompt lists exactly the same alert IDs as the input active list (no drops, no additions).
- [X] T055 [P] [US4] Extend `advisor/backend/tests/test_recommendations_api.py` with two new tests: `ai_narrative` field populated when `ai_narrative.get_narrative` is patched to return a dict; `ai_narrative` is `null` when patched to return `None` AND the `active` list is still returned.
- [X] T056 [P] [US4] Extend `advisor/frontend/src/components/__tests__/RecommendationsPanel.test.tsx` with: renders the AI banner with badge when `ai_narrative` present, hides the banner when `ai_narrative` is null.

**Checkpoint**: User Story 4 fully functional. Run quickstart.md §6.

---

## Phase 7: User Story 5 — Home Assistant forwarding (Priority: P3)

**Goal**: When enabled, critical alerts are forwarded to a Home Assistant webhook with the alert message, device, and timestamp. Delivery failures never halt the evaluation loop. Credentials are masked on readback.

**Independent Test**: Configure a Home Assistant sink via the settings UI, run `POST /settings/notifications/{id}/test`, confirm a 200 and an actual HA notification. Trigger a real critical alert (`service_down`), confirm an HA notification arrives within 30 seconds. Disable the sink; confirm no further notifications. Break the endpoint (point at an unreachable URL); confirm the alert is still recorded locally and backend logs show `ha.delivery_failed`.

### Implementation for User Story 5

- [X] T057 [US5] Create `advisor/backend/app/services/notification_sender.py` exposing `async def deliver(alert: Alert) -> None`. Loads all enabled `notification_sinks` rows whose `min_severity` ≤ `alert.severity`. For each, fires an `httpx.post` to `sink.endpoint` with JSON body `{message, target, severity, created_at}`, 5-second timeout. Logs success/failure as structured JSON. Swallows all exceptions so the engine loop is never impacted (FR-026).
- [X] T058 [US5] Create a small URL-masking helper inside `advisor/backend/app/routers/settings.py` (or a new `app/utils/masking.py` if cleaner) that takes a raw webhook URL and returns a masked version: replace everything after `/api/webhook/` with `***`, or replace the query string if the token is in the query. Used by the sink GET/PUT response serializers.
- [X] T059 [US5] Fill in notification sink endpoints in `advisor/backend/app/routers/settings.py`: `GET /settings/notifications` (returns all sinks with `endpoint_masked`), `POST /settings/notifications` (creates a new sink with Pydantic URL validation), `PUT /settings/notifications/{id}` (partial update; if `endpoint` is omitted, keeps the stored value), `DELETE /settings/notifications/{id}`, and `POST /settings/notifications/{id}/test` (fires a synthetic test payload via `notification_sender` and returns `{ok, status_code, latency_ms}` or `{ok: false, error}`).
- [X] T060 [US5] Update `advisor/backend/app/services/rule_engine.py` notification hook from the T010 stub: after each newly-inserted non-suppressed alert row, `await notification_sender.deliver(alert)`. Increment `ha_notifications_sent` / `ha_notifications_failed` counters in the cycle log.
- [X] T061 [P] [US5] Create `advisor/frontend/src/components/NotificationSinkForm.tsx` — renders the sink (or empty state), fields for name + endpoint (password-type input, shows masked value when editing existing sink) + enabled toggle + min_severity dropdown. Save button POSTs or PUTs. "Test" button calls the test endpoint and shows the result inline.
- [X] T062 [US5] Add the `<NotificationSinkForm />` section to `advisor/frontend/src/pages/Settings.tsx` below the thresholds and mutes sections.

### Tests for User Story 5

- [X] T063 [P] [US5] Create `advisor/backend/tests/test_settings_notifications_api.py`: CRUD round-trip, `endpoint` masked on readback (raw URL never returned by GET), PUT without `endpoint` preserves the stored value, test endpoint success path returns `{ok: true, latency_ms}`, test endpoint failure path returns `{ok: false, error}` with 502.
- [X] T064 [P] [US5] Create `advisor/backend/tests/test_notification_sender.py`: successful POST calls `httpx.post` with the right payload shape, 5-second timeout is enforced, connection errors are swallowed and logged, severity cutoff filters sinks correctly (warning-sink receives warning+critical; critical-sink only critical).
- [X] T065 [P] [US5] Extend `advisor/backend/tests/test_rule_engine.py` with: new active alert triggers a call to `notification_sender.deliver`; suppressed alerts do NOT trigger delivery; delivery failure does NOT halt the cycle; **hot-reload assertion (FR-025)**: with an enabled sink configured, run one cycle (assert `deliver` was called), toggle `notification_sinks.enabled` from `true` to `false` via direct DB update, run a second cycle (assert `deliver` was NOT called on the second cycle), with no engine restart or reconfiguration between the two cycles.
- [X] T066 [P] [US5] Create `advisor/frontend/src/components/__tests__/NotificationSinkForm.test.tsx`: renders masked endpoint when editing existing sink, save button calls right service method, test button shows success/failure inline.

**Checkpoint**: User Story 5 fully functional. Run quickstart.md §5.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Cross-cutting requirements that touch multiple stories — chat grounding (FR-028), observability audit, final quickstart validation.

- [X] T067 Update `advisor/backend/app/services/prompt_assembler.py` to include an `## Active Alerts` section in the system prompt built for the chat feature. Query up to 20 open alerts ordered critical → warning → info, `created_at DESC`. Append a trailing "(N more not shown)" line if more exist. Reuses the same SQL query the recommendations router builds. Satisfies FR-028.
- [X] T068 [P] Create `advisor/backend/tests/test_prompt_assembler_alerts.py`: the assembled prompt contains the `## Active Alerts` heading when alerts exist; contains no such heading when none exist; is capped at 20 alerts with the trailing line; ordering is critical-first.
- [X] T069 [P] Audit `advisor/backend/app/services/rule_engine.py` structured logging to confirm every cycle emits `rule_engine.cycle.completed` with fields `duration_ms`, `rules_evaluated`, `alerts_created`, `alerts_resolved`, `alerts_suppressed`, `alerts_pruned`, `ha_notifications_sent`, `ha_notifications_failed`. Add any missing counters. Satisfies Constitution V observability.
- [X] T070 Run `bash scripts/deploy-advisor.sh` to deploy the feature to HOLYGRAIL, then execute every section of `/Users/jd/Code/camelot/specs/011-recommendations-alerts/quickstart.md` end-to-end and document the results.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies — starts immediately.
- **Phase 2 Foundational**: Depends on Phase 1 completion. BLOCKS all user stories.
- **Phase 3 (US1)**: Depends on Phase 2. Independently testable after completion.
- **Phase 4 (US2)**: Depends on Phase 2. Independently testable. Can run in parallel with Phase 3 if staffed, but both touch `rule_engine.py`, so coordinate.
- **Phase 5 (US3)**: Depends on Phase 2. Needs Phase 3 to be producing alerts for the history to be interesting, but the code is independent. Can run in parallel with Phase 4.
- **Phase 6 (US4)**: Depends on Phase 3 (the recommendations router from T023 is where the narrative is plugged in).
- **Phase 7 (US5)**: Depends on Phase 3 (notification hook is called from the engine when a new alert is inserted, which is Phase 3 functionality).
- **Phase 8 Polish**: Depends on US1 (for the chat grounding query) and is typically run last.

### Within each phase

- Models can be built in parallel (different files).
- Services and routers depend on models.
- Frontend services depend on backend contracts being stable (not on backend implementation being merged — fetch wrappers can be written against the contract doc).
- Tests are written **after** implementation (Constitution IV). Within each phase, test tasks are listed after implementation tasks.

### Parallel opportunities

- **Setup**: T003, T004, T005, T006, T007 all `[P]`.
- **Foundational**: T012, T013, T014, T015 all `[P]` (router shells and page placeholders).
- **US1 rules**: T016–T020, T020a all `[P]` (six different files). T021 must follow them because it edits `rules/__init__.py`.
- **US1 tests**: T027, T028, T029, T030 all `[P]` (different files).
- **US2 frontend components**: T034, T035, T036 all `[P]`. T037 follows because it edits `Settings.tsx`.
- **US2 tests**: T038, T039, T040, T041, T042 all `[P]`.
- **US3 frontend**: T046, T047 parallel; T048 sequential.
- **US3 tests**: T049, T050 `[P]`.
- **US4 tests**: T054, T055, T056 `[P]`.
- **US5 components + tests**: T061 `[P]`, T063–T066 all `[P]`.
- **Polish**: T068, T069 `[P]`.

### Sequential constraints (same file)

- `rule_engine.py` is touched by T010, T022, T033, T060. These MUST run in that order.
- `routers/settings.py` is touched by T012 (shell), T031, T032, T059. These MUST run in that order.
- `routers/recommendations.py` is touched by T012 (shell), T023, T052. These MUST run in that order.
- `routers/alerts.py` is touched by T012 (shell), T043, T044, T045. These MUST run in that order.
- `pages/Settings.tsx` is touched by T015, T037, T062. These MUST run in that order.
- `pages/Alerts.tsx` is touched by T014, T048. These MUST run in that order.
- `components/RecommendationsPanel.tsx` is touched by T025, T053. These MUST run in that order.
- `services/rules/__init__.py` is touched by T008, T021. T021 follows T016–T020a.

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Complete Phase 1 Setup (T001–T007).
2. Complete Phase 2 Foundational (T008–T015).
3. Complete Phase 3 User Story 1 (T016–T030).
4. **STOP and validate**: run quickstart.md §0–1. The MVP is shippable at this point — the admin gets proactive rule-based recommendations on the dashboard with five rules, dedup, lifecycle, cool-down, and sustained-breach protection.

### Incremental delivery

1. MVP (US1) → deploy → demo.
2. Add US2 (thresholds + mutes) → deploy → demo. Admin can tune tolerances and silence noisy alerts.
3. Add US3 (history log) → deploy → demo. Admin can audit the past.
4. Add US4 (AI narrative) → deploy → demo. Nice-to-have polish.
5. Add US5 (HA forwarding) → deploy → demo. Off-dashboard mobile alerts.
6. Polish (T067–T070) → run quickstart.md end to end → mark feature complete.

### Single-developer note

Since this is a single-developer project (Constitution), parallel opportunities are about batching independent edits in one commit rather than splitting work across people. All `[P]` tasks within a phase can be completed in any interleaving.

---

## Notes

- `[P]` tasks touch different files and have no in-phase dependencies.
- `[Story]` labels map tasks to user stories for traceability.
- Tests are written **after** implementation per Constitution IV (Test-After).
- Commit after each task or small logical group.
- Do not skip checkpoints — each is a clean demo boundary.
- When in doubt about a rule's internals, reread `data-model.md §2` and the corresponding rule row in `research.md §3`.
