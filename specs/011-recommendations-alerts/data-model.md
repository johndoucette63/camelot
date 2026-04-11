# Data Model: Recommendations & Alerts

**Feature**: 011-recommendations-alerts
**Date**: 2026-04-10
**Migration**: `advisor/backend/migrations/versions/004_recommendations_alerts.py`

This document defines the durable schema and in-process domain types for the rule engine. Persistent entities map to SQLAlchemy models under `advisor/backend/app/models/`; in-memory types live under `advisor/backend/app/services/rules/`.

---

## 1. Persistent entities (PostgreSQL)

### 1.1 `alerts` (extended — existing table)

Extends the existing `alerts` table created in migration `002_service_registry`. Columns added / modified by migration 004 are marked **NEW** or **CHANGED**.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `INTEGER` (PK) | no | `serial` | Existing |
| `device_id` | `INTEGER` FK `devices.id` | yes | — | Existing. Retained for backward-compat and join convenience. |
| `service_id` | `INTEGER` FK `services.id` | yes | — | Existing. Same as above. |
| `severity` | `VARCHAR(20)` | no | — | Existing. `info` \| `warning` \| `critical`. Rule-provided, never runtime-escalated (FR-002). |
| `message` | `TEXT` | no | — | Existing. The human-readable alert message shown in the dashboard and log. |
| `created_at` | `TIMESTAMP` | no | `now()` | Existing. When the alert instance was first created (FR-012). |
| `acknowledged` | `BOOLEAN` | — | — | **CHANGED**: column dropped in migration 004; its information is now carried by `state = 'acknowledged'` (FR-005). |
| `rule_id` | `VARCHAR(100)` | no | — | **NEW**. Stable string identifier of the rule that fired (e.g. `pi_cpu_high`). Matches `Rule.id` in the Python registry. |
| `target_type` | `VARCHAR(20)` | no | — | **NEW**. `device` \| `service` \| `system`. `system` is used for rules with no per-device target (e.g. `ollama_unavailable`). |
| `target_id` | `INTEGER` | yes | — | **NEW**. Either a `devices.id` or `services.id` depending on `target_type`, or `NULL` when `target_type='system'`. Foreign keys are NOT enforced (to allow either target table) — integrity is validated in the engine. |
| `state` | `VARCHAR(20)` | no | `'active'` | **NEW**. `active` \| `acknowledged` \| `resolved`. State machine defined in §3. |
| `acknowledged_at` | `TIMESTAMP` | yes | — | **NEW**. Set when `state` transitions `active → acknowledged`. Never cleared. |
| `resolved_at` | `TIMESTAMP` | yes | — | **NEW**. Set when `state` transitions to `resolved`. Drives the 10-minute cool-down predicate (FR-006b). |
| `resolution_source` | `VARCHAR(10)` | yes | — | **NEW**. `auto` \| `manual`. `auto` = the rule condition cleared; `manual` = admin resolved from the UI. Null while `active` or `acknowledged`. |
| `source` | `VARCHAR(10)` | no | `'rule'` | **NEW**. `rule` \| `ai`. AI-assisted recommendations (FR-018) use `ai`. |
| `suppressed` | `BOOLEAN` | no | `false` | **NEW**. `true` if a `(rule, target)` mute was active when the rule fired (FR-011b). A suppressed row is visible in the log but never counted as active. |

**Indexes added in migration 004**:

- `alerts_active_rule_target_uidx` — unique partial index on `(rule_id, target_type, target_id)` `WHERE state != 'resolved' AND suppressed = false`. This is the database-level enforcement of FR-004 (dedup by `(rule_id, target_id)`).
- `alerts_state_created_at_idx` — on `(state, created_at DESC)`, accelerates the alert history filter query (SC-005).
- `alerts_rule_target_resolved_at_idx` — on `(rule_id, target_type, target_id, resolved_at DESC)`, used by the cool-down predicate.

**Validation rules (enforced in engine, not DB)**:

- `target_id IS NULL` if and only if `target_type = 'system'`.
- `severity IN ('info','warning','critical')`.
- `state` transitions: `active → acknowledged → resolved`, `active → resolved`, `acknowledged → active` (NOT allowed), `resolved → *` (NOT allowed — re-firing creates a new row per Q1 clarification).
- `resolved_at IS NOT NULL` ⟺ `state = 'resolved'`.
- `acknowledged_at IS NOT NULL` ⟺ `state IN ('acknowledged','resolved')` and the instance was acknowledged before being resolved.

---

### 1.2 `alert_thresholds` (NEW)

Stores user-tunable metric thresholds (FR-007–FR-011). Rules look up values here at evaluation time.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `key` | `VARCHAR(100)` PK | no | — | Stable identifier, e.g. `cpu_percent`, `disk_percent`, `ping_latency_ms`, `memory_percent`, `service_down_minutes`. |
| `value` | `NUMERIC(10,2)` | no | — | Current effective value. |
| `unit` | `VARCHAR(20)` | no | — | Display unit for the UI (e.g. `%`, `ms`, `minutes`). |
| `default_value` | `NUMERIC(10,2)` | no | — | Shipped default, used by the settings UI to show "reset to default". |
| `min_value` | `NUMERIC(10,2)` | no | — | Lower bound enforced on save (FR-010). |
| `max_value` | `NUMERIC(10,2)` | no | — | Upper bound enforced on save (FR-010). |
| `updated_at` | `TIMESTAMP` | no | `now()` | Last modification time, surfaced in the settings UI. |

**Seed rows** (inserted by migration 004):

| key | value | default_value | unit | min | max |
|---|---|---|---|---|---|
| `cpu_percent` | 80 | 80 | `%` | 10 | 100 |
| `disk_percent` | 85 | 85 | `%` | 10 | 100 |
| `service_down_minutes` | 5 | 5 | `minutes` | 1 | 1440 |
| `device_offline_minutes` | 10 | 10 | `minutes` | 1 | 1440 |

**Validation**:

- `value` must be in `[min_value, max_value]` — enforced in the settings router at save time (FR-010). The router returns HTTP 400 with the violated constraint on rejection.
- `key` is immutable; new thresholds require a code change + migration.

---

### 1.3 `rule_mutes` (NEW)

TTL-bound suppressions for `(rule_id, target_id)` pairs (FR-011a–FR-011c, Q4 clarification).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `INTEGER` PK | no | `serial` | — |
| `rule_id` | `VARCHAR(100)` | no | — | Matches the string in `alerts.rule_id`. |
| `target_type` | `VARCHAR(20)` | no | — | `device` \| `service` \| `system`. |
| `target_id` | `INTEGER` | yes | — | `NULL` when `target_type='system'`. |
| `created_at` | `TIMESTAMP` | no | `now()` | When the mute was created. |
| `expires_at` | `TIMESTAMP` | no | — | Absolute expiry. Mute is active iff `now() < expires_at AND cancelled_at IS NULL`. |
| `cancelled_at` | `TIMESTAMP` | yes | — | Set when the admin cancels a mute early (FR-011c). |
| `note` | `TEXT` | yes | — | Optional admin-provided reason. |

**Indexes**:

- `rule_mutes_active_idx` — partial index on `(rule_id, target_type, target_id)` `WHERE cancelled_at IS NULL AND expires_at > now()` is not portable; instead use `(rule_id, target_type, target_id, expires_at DESC, cancelled_at)` and let the engine filter. A simple composite is fine at this scale.

**Validation**:

- `expires_at > now()` at creation time.
- `note` ≤ 500 characters.
- Cancelling a mute is idempotent: repeated cancel calls return 200 with no change.

---

### 1.4 `notification_sinks` (NEW)

Configuration for optional outbound notification targets. V1 supports one type (`home_assistant`) and one row at a time, but the schema is shaped to allow future sink types without a migration.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `INTEGER` PK | no | `serial` | — |
| `type` | `VARCHAR(30)` | no | — | Sink type. V1: `home_assistant`. |
| `name` | `VARCHAR(100)` | no | — | Human-readable label shown in settings UI. |
| `enabled` | `BOOLEAN` | no | `false` | Master switch (FR-025). |
| `endpoint` | `TEXT` | no | — | For `home_assistant`: the full webhook URL including any trailing token path. Stored verbatim; masked on read. |
| `min_severity` | `VARCHAR(20)` | no | `'critical'` | Minimum severity forwarded (FR-023). `info` \| `warning` \| `critical`. |
| `created_at` | `TIMESTAMP` | no | `now()` | — |
| `updated_at` | `TIMESTAMP` | no | `now()` | Bumped on any field change. |

**Validation**:

- `type IN ('home_assistant')` for v1.
- `endpoint` must be an HTTP/HTTPS URL — enforced in the router with Pydantic.
- `min_severity IN ('info','warning','critical')`.
- On `GET /settings/notifications`, the `endpoint` field is masked in the response (§5 of research.md). The full URL is never echoed back.

---

### 1.5 `unknown_device_observations` — *not introduced*

The unknown-device rule uses the existing device scanner output plus its rolling-window heuristic (research.md §6). No new table is required — the rule iterates over the current scan + previous scans from the existing F4.2 `scan` records and computes "seen in ≥3 consecutive scans over ≥30 minutes" on the fly. Dismissed-guest state, if needed later, can be a follow-up. This is a deliberate YAGNI choice.

The Key Entities section of the spec lists "Unknown Device Observation" as a conceptual entity; in the implementation it collapses into a computed projection over `scans`, not a persisted row.

---

## 2. In-process domain types (Python)

These live in `advisor/backend/app/services/rules/` and are NOT persisted.

### 2.1 `Rule` (base class — `rules/base.py`)

```python
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

Severity = Literal["info", "warning", "critical"]
TargetType = Literal["device", "service", "system"]

@dataclass
class RuleResult:
    target_type: TargetType
    target_id: int | None  # None when target_type == "system"
    message: str           # human-readable, used as alerts.message

class Rule:
    id: str                # e.g. "pi_cpu_high"
    name: str              # e.g. "Sustained high CPU on Pi"
    severity: Severity
    sustained_window: timedelta = timedelta(minutes=5)  # rule may override; 0 means "fire on first observation"

    async def evaluate(self, ctx: "RuleContext") -> list[RuleResult]:
        """Return all currently-breached targets. The engine handles dedup, lifecycle, mute, and delivery."""
        raise NotImplementedError
```

### 2.2 `RuleContext` (`rules/base.py`)

A per-cycle immutable snapshot assembled once by the engine and passed to every rule:

```python
@dataclass
class RuleContext:
    now: datetime                              # UTC
    session: AsyncSession                      # SQLAlchemy async session
    devices: list[Device]                      # all devices in inventory
    services: list[Service]                    # all services in registry
    health_results: dict[int, HealthCheckResult]  # keyed by service_id, latest per service
    container_state: dict                      # from app.state.container_state
    thresholds: dict[str, Decimal]             # materialized from alert_thresholds table
    ollama_healthy: bool                       # result of a lightweight Ollama probe
    recent_scans: list[Scan]                   # last N scans from F4.2 for unknown-device detection
```

### 2.3 Rule catalog (`rules/__init__.py`)

A flat list of instantiated rules. Engine iterates over this list each cycle:

```python
RULES: list[Rule] = [
    PiCpuHighRule(),
    DiskHighRule(),
    ServiceDownRule(),
    OllamaUnavailableRule(),
    UnknownDeviceRule(),
]
```

Adding a sixth rule is a one-file change plus an entry in this list — versioned with the code per FR-002's "Rules are static" entity definition.

### 2.4 Per-rule specifics

| Rule ID | Target | Severity | Threshold key(s) | Condition summary |
|---|---|---|---|---|
| `pi_cpu_high` | `device` (Pis only) | `warning` | `cpu_percent` | Latest CPU% for the device is ≥ threshold; sustained 5 min. |
| `disk_high` | `device` | `warning` | `disk_percent` | Any mounted filesystem's usage% is ≥ threshold. No sustained window (disk fills monotonically). |
| `service_down` | `service` | `critical` | `service_down_minutes` | Latest `health_check_result.status = 'down'` for ≥ threshold minutes. |
| `device_offline` | `device` | `warning` | `device_offline_minutes` | Device has reported no metrics for ≥ threshold minutes AND has at least one prior metric on record (never-seen devices are skipped to avoid false positives on the first scan after deploy). No sustained window — the threshold itself defines the grace period. |
| `ollama_unavailable` | `system` (target_id=NULL) | `info` | — | `ctx.ollama_healthy == False`. No sustained window. |
| `unknown_device` | `device` (synthesized or null) | `warning` | — | MAC appears in ≥3 consecutive scans spanning ≥30 minutes and not in the known inventory. Target is the unknown device's MAC carried in the message; `target_type='system'`, `target_id=NULL` for dedup purposes, with the MAC embedded as a stable suffix of the `rule_id` (e.g. `unknown_device:aa:bb:cc:dd:ee:ff`) so dedup works per MAC. |

**Note on `unknown_device` dedup key**: Since the target is not a row in `devices`, we piggyback on the `rule_id` string by appending the MAC. This avoids adding a generic `target_key` column just for one rule. The base `rule_id` shown in settings/mutes UI is still `unknown_device` — the engine strips the MAC suffix when rendering.

---

## 3. State machine: alert instance lifecycle

```
         [rule fires]
              │
              ▼
         ┌─────────┐   admin ack       ┌───────────────┐
         │ active  │ ────────────────▶ │ acknowledged   │
         └─────────┘                   └───────────────┘
              │                                │
   condition  │                     admin      │
   clears OR  │                     resolve    │
   admin      │                                │
   resolve    │                                │
              ▼                                ▼
         ┌─────────────────────────────────────────┐
         │                 resolved                 │
         └─────────────────────────────────────────┘
              │
              │  (10-minute cool-down)
              │
              ▼
         [new instance may fire]
```

- `active → acknowledged`: user action, `acknowledged_at = now()`.
- `active → resolved`: auto (condition cleared) or manual. Sets `resolved_at` and `resolution_source`.
- `acknowledged → resolved`: same as above.
- `acknowledged → active`: NOT allowed. A condition that re-fires after ack is modeled as the same instance staying in `acknowledged`; ack does not clear the condition.
- `resolved → *`: NOT allowed. Re-firing creates a new row (Q1 clarification).

The invariant `active + acknowledged` states are the only "open" states. The partial unique index on `(rule_id, target_type, target_id) WHERE state != 'resolved' AND suppressed = false` enforces at most one open instance per `(rule, target)`.

---

## 4. Data flow per engine cycle

Each cycle the engine executes these steps in order:

1. **Build `RuleContext`**: one async DB query fan-out that loads devices, services, latest health results, thresholds, and a cheap Ollama health probe.
2. **Evaluate rules**: each `Rule.evaluate(ctx)` returns a list of `RuleResult`. Results are collected by the engine.
3. **Sustained window filter**: for each `RuleResult`, update the in-memory "first seen" streak map. Drop results whose streak is shorter than `rule.sustained_window`.
4. **Cool-down filter**: for each remaining result, query `SELECT 1 FROM alerts WHERE rule_id=... AND target_*=... AND state='resolved' AND resolved_at > now() - INTERVAL '10 minutes'`. Drop matches.
5. **Mute check**: for each remaining result, check for an active `rule_mutes` row for the same `(rule_id, target_type, target_id)`. If muted, insert the alert with `suppressed=true` and skip delivery to Home Assistant.
6. **Insert / ignore**: attempt `INSERT ... ON CONFLICT DO NOTHING` against the partial unique index. Successful inserts are "newly active" alerts.
7. **Auto-resolve check**: for every currently open alert (`state != 'resolved'`), evaluate whether its condition still holds by re-querying the rule with the same target. If the condition cleared, UPDATE the row to `state='resolved', resolved_at=now(), resolution_source='auto'`.
8. **Notify Home Assistant**: for each newly active, non-suppressed alert whose severity is ≥ any enabled sink's `min_severity`, fire `httpx.post` with a 5-second timeout. Log failures.
9. **Cleanup**: delete rows from `alerts` whose `resolved_at < now() - 30 days` (FR-015 retention pruning). Purge expired in-memory streaks.

Cycle duration is logged as a structured field for observability (Constitution V).

---

## 5. Retention and pruning

- `alerts` rows older than 30 days (`resolved_at < now() - 30 days`, or `created_at < now() - 30 days AND state='resolved'`) are deleted during the engine cycle cleanup step.
- `rule_mutes` rows are kept indefinitely as an audit trail; expired mutes are filtered out by query rather than deleted. A manual cleanup of `rule_mutes` older than 90 days can be added later if it becomes noisy — out of scope for v1.
- `alert_thresholds` and `notification_sinks` are user-owned configuration and never pruned.

---

## 6. Summary of new SQLAlchemy models

| File | Class | Table |
|---|---|---|
| `models/alert.py` | `Alert` | `alerts` (extended) |
| `models/alert_threshold.py` | `AlertThreshold` | `alert_thresholds` |
| `models/rule_mute.py` | `RuleMute` | `rule_mutes` |
| `models/notification_sink.py` | `NotificationSink` | `notification_sinks` |

All four use the existing `Base` from `app/database.py` and match the SQLAlchemy 2.0 `Mapped[...]` / `mapped_column()` style already used by F4.2–F4.4.
