# Implementation Plan: Recommendations & Alerts

**Branch**: `011-recommendations-alerts` | **Date**: 2026-04-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/Users/jd/Code/camelot/specs/011-recommendations-alerts/spec.md`

## Summary

Add a rule-based recommendation engine on top of the advisor's existing device inventory (F4.2), service registry / health checks (F4.3), and the existing `alerts` table. The engine evaluates a fixed catalog of at least five Python-defined rules on every cycle, creating, resolving, and deduplicating alert instances by `(rule_id, target_id)`, tracking lifecycle `active → acknowledged → resolved`, enforcing a 5-minute sustained-breach window and a 10-minute post-resolution cool-down, and honoring per-(rule, target) TTL mutes. The dashboard gets a recommendations panel, an alerts history page with severity/device/date filters and manual ack/resolve, and a settings page for thresholds and active mutes. An optional AI layer calls Ollama on demand to consolidate co-firing alerts into a narrative and explain anomalies, and degrades gracefully when Ollama is unavailable. An optional Home Assistant webhook forwards critical alerts (configurable severity cutoff).

Technical approach: reuse the existing `asyncio` background loop pattern from `health_checker.py` for a new `rule_engine.py` that runs alongside container discovery and health checks in the advisor backend. Extend the existing `alerts` table via a new Alembic migration (`004_recommendations_alerts.py`) to add lifecycle columns (`rule_id`, `target_type`, `target_id`, `state`, `acknowledged_at`, `resolved_at`, `resolution_source`, `source`, `suppressed`) rather than introducing a parallel table. Add three small new tables: `alert_thresholds` (persisted user-tunable values), `rule_mutes` (TTL suppressions), and `notification_sinks` (Home Assistant webhook config). Rules themselves live in Python as a static registry so they version with the code per the constitution's YAGNI principle. The AI narrative is generated lazily at dashboard-read time by extending the existing `prompt_assembler.py` + `ollama_client.py` pair from F4.4, with a short in-memory TTL cache so repeat dashboard polls don't re-hit Ollama. Home Assistant delivery is a small async `httpx` POST inside the engine loop. Frontend adds an `Alerts` page, a `Settings` page, and a recommendations panel component on the existing `Home` page — all following the existing `advisor/frontend/src/pages/` + `components/` convention.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 (frontend)
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14, `httpx` 0.28 (for Ollama + Home Assistant webhook calls, already in `requirements.txt`), Pydantic v2; React 18, Vite 6, Tailwind 3, react-router-dom 7, TanStack React Table 8 (used for the alert history table)
**Storage**: PostgreSQL 16 in the existing `advisor_pgdata` Docker volume. Extended via a new Alembic migration `004_recommendations_alerts.py` which (a) adds lifecycle + rule columns to the existing `alerts` table, (b) creates `alert_thresholds`, `rule_mutes`, and `notification_sinks` tables
**Testing**: pytest + pytest-asyncio + httpx AsyncClient (backend, existing pattern under `advisor/backend/tests/`); Vitest + @testing-library/react (frontend, existing pattern under `advisor/frontend/src/components/__tests__/`)
**Target Platform**: Docker Compose stack on HOLYGRAIL (Ubuntu 24.04, x86_64). Backend and frontend already containerized under `advisor/docker-compose.yml`. Ollama runs in a sibling Compose stack at `http://ollama:11434` (container network) or `http://holygrail:11434` (host). Home Assistant (when enabled) is reachable over the LAN at a user-supplied URL
**Project Type**: Web application (backend + frontend monorepo under `advisor/`)
**Performance Goals**: Engine evaluation cycle completes in <2 s for the home-scale fleet (≤10 devices, ≤50 services) (supports SC-001 and SC-003). Alert-log filter queries return in <2 s for thousands of rows (SC-005). First AI narrative token within 3 s when Ollama is healthy; absent entirely within 500 ms when Ollama is unreachable (SC-006). Home Assistant webhook delivery within 30 s of rule firing (SC-007)
**Constraints**: Local-only — Ollama and Home Assistant are both reached over the LAN; no external API calls (Constitution I). Single-admin deployment, no auth gate added (inherits the advisor app's LAN-trusted posture). AI layer MUST degrade gracefully: rule-based evaluation, persistence, and delivery to Home Assistant MUST continue uninterrupted when Ollama is slow or unreachable. The Home Assistant integration is optional and the feature ships useful without it. Integration credentials (webhook tokens) MUST be stored in the DB but never echoed back to the UI in plaintext after save (FR-027)
**Scale/Scope**: Single admin, ≤10 devices, ≤50 services, at most low tens of active alerts at any given time, thousands of historical alerts over the 30-day retention window. Five shipped rules in v1; adding a sixth rule is a code change, not a DB change

## Constitution Check

Evaluated against `.specify/memory/constitution.md` v1.1.0.

| Principle | Assessment |
| --- | --- |
| **I. Local-First** | PASS. All evaluation, persistence, AI inference (Ollama), and optional notification delivery (Home Assistant) happens on the LAN. No cloud APIs, no telemetry, no external auth. |
| **II. Simplicity & Pragmatism** | PASS. Extends the existing `alerts` table rather than creating a parallel schema. Rules live as a static Python registry — no rule DSL, no DB-driven rule editor, no plugin system. Engine is a single async loop in the existing backend process, reusing the `health_checker.py` pattern. Home Assistant delivery is a direct `httpx.post` with no broker, no queue, no retry daemon. AI narrative is a lazy read-time call with a small TTL cache, not a background worker. No new services, no new containers, no new languages. |
| **III. Containerized Everything** | PASS. Feature ships inside the existing `advisor` backend + frontend containers under `advisor/docker-compose.yml`. No new containers. Ollama is an existing container. Home Assistant is an external endpoint, not something we host. |
| **IV. Test-After (Not Test-First)** | PASS. Implementation is written first; tests follow using the existing pytest + Vitest harnesses. `/speckit.tasks` will order implementation-before-tests. |
| **V. Observability** | PASS. The rule engine emits structured JSON log lines for each cycle (rules evaluated, alerts created / resolved / suppressed, duration). The existing `/health` endpoint still covers liveness. Failures to deliver to Home Assistant are logged with context but MUST NOT halt the evaluation loop (FR-026). Constitution V calls out that critical alerts MUST be surfaced in the advisor dashboard — this feature is the vehicle that satisfies that requirement. |

**Result**: No violations. Proceeding with Phase 0 research.

## Project Structure

### Documentation (this feature)

```text
specs/011-recommendations-alerts/
├── plan.md              # This file
├── spec.md              # Feature spec (written, clarified)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── alerts-api.md    # REST contract for /alerts, /recommendations, /settings/thresholds, /settings/mutes, /settings/notifications
└── checklists/
    └── requirements.md  # Spec quality checklist (already exists)
```

### Source Code (repository root)

```text
advisor/
├── backend/
│   ├── app/
│   │   ├── main.py                             # EDIT: start rule_engine background task alongside health_checker
│   │   ├── config.py                           # EDIT: add HA_WEBHOOK_* env fallbacks, rule engine cadence
│   │   ├── models/
│   │   │   ├── alert.py                        # EDIT: add rule_id, target_type, target_id, state, acknowledged_at, resolved_at, resolution_source, source, suppressed
│   │   │   ├── alert_threshold.py              # NEW: persisted threshold row (metric, value, unit)
│   │   │   ├── rule_mute.py                    # NEW: per-(rule, target) TTL mute
│   │   │   └── notification_sink.py            # NEW: Home Assistant webhook config
│   │   ├── routers/
│   │   │   ├── alerts.py                       # NEW: GET list + filters, POST /{id}/acknowledge, POST /{id}/resolve
│   │   │   ├── recommendations.py              # NEW: GET active recommendations + narrative for dashboard panel
│   │   │   └── settings.py                     # NEW: thresholds, mutes, notification sinks CRUD
│   │   ├── services/
│   │   │   ├── rule_engine.py                  # NEW: background async loop — evaluates rules, manages lifecycle, enforces dedup/sustained-window/cool-down/mute, drives HA webhook
│   │   │   ├── rules/
│   │   │   │   ├── __init__.py                 # NEW: rule registry
│   │   │   │   ├── base.py                     # NEW: Rule base class + RuleContext + RuleResult
│   │   │   │   ├── pi_cpu_high.py              # NEW: sustained high Pi CPU → warning
│   │   │   │   ├── disk_high.py                # NEW: disk usage > threshold → warning
│   │   │   │   ├── service_down.py             # NEW: service down > 5 min → critical
│   │   │   │   ├── device_offline.py           # NEW: device metrics stale > 10 min → warning
│   │   │   │   ├── ollama_unavailable.py       # NEW: Ollama unreachable → info
│   │   │   │   └── unknown_device.py           # NEW: persistent unknown device on LAN → warning
│   │   │   ├── ai_narrative.py                 # NEW: builds consolidated narrative via Ollama; TTL cache; graceful degradation
│   │   │   ├── notification_sender.py          # NEW: POSTs critical alerts to Home Assistant webhook; logs + swallows failures
│   │   │   └── prompt_assembler.py             # EDIT: include active alerts + recommendations in chat grounding (FR-028)
│   │   └── database.py                         # (no change expected)
│   ├── migrations/versions/
│   │   └── 004_recommendations_alerts.py       # NEW: extend alerts + add alert_thresholds, rule_mutes, notification_sinks
│   └── tests/
│       ├── test_rule_engine.py                 # NEW: cycle, dedup, sustained-window, cool-down, mute suppression, auto-resolve
│       ├── test_rules_catalog.py               # NEW: each of the 5 seeded rules against synthetic inputs
│       ├── test_alerts_api.py                  # NEW: list/filter/ack/resolve endpoints
│       ├── test_recommendations_api.py         # NEW: dashboard panel shape + AI narrative graceful-fail
│       ├── test_settings_api.py                # NEW: thresholds, mutes, notification sinks CRUD + credential redaction
│       ├── test_notification_sender.py         # NEW: HA webhook success + failure paths
│       └── test_ai_narrative.py                # NEW: narrative build + Ollama unavailable fallback
└── frontend/
    └── src/
        ├── App.tsx                             # EDIT: add /alerts and /settings routes; nav link for each
        ├── pages/
        │   ├── Alerts.tsx                      # NEW: history table with severity/device/date filters, ack/resolve actions
        │   ├── Settings.tsx                    # NEW: thresholds, active mutes, notification sinks
        │   └── Home.tsx                        # EDIT: mount <RecommendationsPanel /> on the dashboard
        ├── components/
        │   ├── RecommendationsPanel.tsx        # NEW: active recommendations + AI narrative banner (marked as AI-assisted)
        │   ├── AlertRow.tsx                    # NEW: one row in the alert history table
        │   ├── ThresholdForm.tsx               # NEW: edit threshold values with client-side validation
        │   ├── MuteList.tsx                    # NEW: active mutes + cancel-early + TTL countdown
        │   ├── NotificationSinkForm.tsx        # NEW: HA webhook URL + enable toggle + severity cutoff; redacted read-back
        │   └── __tests__/
        │       ├── RecommendationsPanel.test.tsx
        │       ├── ThresholdForm.test.tsx
        │       └── AlertRow.test.tsx
        ├── services/
        │   ├── alerts.ts                       # NEW: fetch wrapper for /alerts/*
        │   ├── recommendations.ts              # NEW: fetch wrapper for /recommendations
        │   └── settings.ts                     # NEW: fetch wrapper for /settings/*
        └── types.ts                            # EDIT: add Alert, Recommendation, Threshold, RuleMute, NotificationSink types
```

**Structure Decision**: Slots entirely into the existing `advisor/` monorepo. Backend additions follow the established `models/`, `routers/`, `services/`, `tests/` convention used by F4.2–F4.4. The new `services/rules/` subdirectory is the only new sub-folder — it holds one Python module per rule so adding a sixth rule in the future is a single-file change. Frontend additions follow the existing `pages/` + `components/` + `services/` layout. No new top-level directories, no new Compose stacks.

## Complexity Tracking

No constitution violations require justification. Table intentionally empty.
