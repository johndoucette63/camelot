# Research: Recommendations & Alerts

**Feature**: 011-recommendations-alerts
**Date**: 2026-04-10
**Purpose**: Resolve the open design decisions surfaced during `/speckit.plan`. No `NEEDS CLARIFICATION` markers remain in spec or plan; the items below are conscious implementation choices that need to be captured before Phase 1.

---

## 1. Alerts-table schema: extend vs. parallel

**Decision**: Extend the existing `alerts` table (from F4.3 / migration `002_service_registry.py`) via a new Alembic migration, rather than creating a parallel `alert_instances` table.

**Rationale**:
- The existing table already holds `severity`, `message`, `acknowledged`, `device_id`, `service_id`, `created_at` — four of the six fields the new spec needs. Rebuilding a parallel schema would strand those columns and force the existing `ai_context` / `dashboard` routers to dual-read.
- Spec FR-005 requires instance lifecycle (`active → acknowledged → resolved`) and FR-004 requires `(rule_id, target_id)` deduplication. Both can be added as columns + a partial unique index without touching the existing primary key.
- Constitution II (Simplicity & Pragmatism) explicitly calls out YAGNI. One table with added columns is simpler than two tables with a compatibility shim.
- The existing `device_id`/`service_id` nullable columns generalize to a `target_type` + `target_id` pair without a data loss, but the migration can keep both representations during the transition window — in practice it's easier to introduce a unified `target_type` enum + `target_id` and backfill from `device_id` / `service_id` in one pass since no historical alert data needs to be preserved across the schema change (advisor is not yet in production).

**Alternatives considered**:
- *Parallel `alert_instances` table*: Rejected. Would duplicate storage, complicate the chat grounding path, and violate YAGNI.
- *Keep the table exactly as-is and track state externally*: Rejected. State must survive restart (FR-009/FR-014) and filter queries (SC-005) need a state column in the same row.

**Migration plan**:
1. `alembic revision -m "recommendations_alerts"` generates `004_recommendations_alerts.py`.
2. Upgrade adds: `rule_id VARCHAR(100)`, `target_type VARCHAR(20)` (`device` | `service` | `system`), `target_id INTEGER NULLABLE` (nullable because `system`-targeted rules like "Ollama unavailable" have no target row), `state VARCHAR(20) NOT NULL DEFAULT 'active'`, `acknowledged_at TIMESTAMP NULLABLE`, `resolved_at TIMESTAMP NULLABLE`, `resolution_source VARCHAR(10) NULLABLE` (`auto` | `manual`), `source VARCHAR(10) NOT NULL DEFAULT 'rule'` (`rule` | `ai`), `suppressed BOOLEAN NOT NULL DEFAULT false`.
3. Partial unique index `alerts_active_rule_target_uidx` on `(rule_id, target_type, target_id)` `WHERE state != 'resolved'` to enforce FR-004 at the database level.
4. Separate index on `(state, created_at DESC)` to accelerate the history filter query (SC-005).
5. The existing `acknowledged BOOLEAN` column is dropped — its information is carried by `state = 'acknowledged'`.

---

## 2. Engine evaluation loop: placement and cadence

**Decision**: A single async background task in the existing FastAPI app process, started on app startup via `asyncio.create_task()` alongside the existing `fetch_containers` and `run_health_checks` loops in `health_checker.py`. Default cadence is 60 seconds, configurable via `RULE_ENGINE_INTERVAL_SECONDS` env var.

**Rationale**:
- Reuses the exact pattern already established in `services/health_checker.py` (which has its own 60-second loop). No new scheduler library, no new container, no APScheduler dependency. Constitution II.
- The spec says "evaluation cycle aligns with the advisor's existing data refresh cadence" (Assumption #5). Running on the same 60-second heartbeat as the health checker means every cycle has fresh `health_check_results` to read from.
- Single-admin, tiny fleet — async coroutines in the existing event loop have plenty of headroom. A dedicated worker process would be over-engineering.
- Failure isolation: the engine's top-level `while True:` wraps each cycle in `try/except Exception` and logs the traceback before sleeping, exactly like `health_checker.py` does, so a bug in one rule does not kill the loop.

**Alternatives considered**:
- *APScheduler*: Rejected. Adds a dependency for a single periodic task; `asyncio.sleep` is sufficient.
- *Separate worker container*: Rejected. Doubles deploy complexity and cross-process DB coordination for no benefit at single-admin scale.
- *Run inside the health checker loop directly*: Rejected. Separation of concerns — one loop watches containers/ports, the other evaluates rules over the resulting state.

**Sustained-breach tracking**: The 5-minute sustained requirement (FR-006a) is tracked with a per-process `dict[(rule_id, target_id), datetime]` that records the *first* time the condition was seen breached in the current streak. When the condition clears for a cycle, the entry is deleted. When `now - first_seen >= 5 min`, the rule fires and the entry remains until the condition clears (avoiding re-firing while the alert is already active). This state is in-memory only — a process restart resets the streak clock, which is acceptable for a home-lab (we'd rather re-observe the condition than persist a cache table).

**Cool-down tracking** (FR-006b): The post-resolution cool-down is enforced by a WHERE clause when the engine checks whether it's allowed to create a new instance — `AND NOT EXISTS (SELECT 1 FROM alerts WHERE rule_id = $1 AND target_id = $2 AND state = 'resolved' AND resolved_at > NOW() - INTERVAL '10 minutes')`. This is durable across restarts because it reads from the DB, and it avoids maintaining a second in-memory map.

---

## 3. Rule definition: Python registry vs. DB-driven

**Decision**: Rules are defined as small Python modules under `app/services/rules/`, each exporting a single `Rule` subclass. A registry in `rules/__init__.py` holds the list of active rule instances. Adding a rule is a code change and a code review; rules are not editable via the UI.

**Rationale**:
- FR-002 requires exactly five shipped rules. Five concrete conditions, each with a small amount of logic, is trivially readable as five Python files.
- The Key Entities section of the spec explicitly says "Rules are static and versioned with the advisor code." That is an intentional scope decision.
- Rule conditions refer to live DB state (devices, services, health_check_results) via SQLAlchemy. Expressing that in a DSL or JSON ruleset would immediately be less clear and more buggy than the equivalent Python.
- Thresholds *are* user-tunable (FR-008) and live in the `alert_thresholds` table. Each rule reads its threshold by key at evaluation time. This keeps the "tune without code change" promise without introducing a rule engine.

**Alternatives considered**:
- *JSON / YAML rule files*: Rejected. For five rules it's more code, not less — we'd need a parser, a validator, a DSL, and the rules would be harder to step through in a debugger.
- *DB-driven rules with a UI editor*: Rejected. Out of scope; far more complex than needed; no user asked for it.

**Rule base interface** (pseudocode, fleshed out in Phase 1 data-model):

```python
class Rule:
    id: str                  # stable identifier, e.g. "pi_cpu_high"
    name: str                # human-readable
    severity: Literal["info","warning","critical"]
    sustained_window: timedelta = timedelta(minutes=5)  # default; rule can override
    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]: ...
```

`RuleContext` is a dataclass the engine builds once per cycle containing async DB session, current devices, current services, latest health check results, container state, and threshold lookups. `RuleResult` carries `target_type`, `target_id`, and `message` — the engine converts results to alert instances and handles dedup/cool-down/mute/HA-forwarding centrally.

---

## 4. AI narrative: when and how to call Ollama

**Decision**: AI narrative is generated on demand when the dashboard or chat fetches the current recommendations, not on every rule engine cycle. Results are cached in a simple in-process TTL cache keyed by the sorted tuple of active alert IDs. TTL is 60 seconds (matches the engine cadence, so one cycle = one narrative call max). Cache miss triggers an Ollama call with a short total budget (10 s); on timeout or connection error, the narrative field is simply omitted from the response. The rule-based alert list is returned either way (FR-020).

**Rationale**:
- Engine-time generation would burn Ollama capacity and DB writes even when nobody is looking at the dashboard. Single-admin traffic is zero most of the time.
- Caching on "set of active alert IDs" means that during a steady-state incident the narrative is built once and reused until something changes (alert added, alert resolved).
- The spec requires graceful degradation (FR-020) and bounded latency visibility. A hard 10-second timeout around the Ollama call keeps the dashboard responsive even when Ollama is slow.
- Reuses the existing `ollama_client.py` and the prompt-assembly pattern from F4.4. The new `ai_narrative.py` is roughly 100 lines.

**Alternatives considered**:
- *Pre-generate on every engine cycle*: Rejected. Wasteful when nobody is looking.
- *Precompute and persist to the DB*: Rejected. Adds a schema field, cache invalidation, and doesn't match the lazy dashboard-fetch usage pattern.
- *Server-sent stream to the dashboard*: Rejected. Overkill for a short narrative paragraph and introduces a second streaming code path beyond chat.

**Prompt shape**: A compact system prompt instructing the model to consolidate rule-based alerts into a narrative, explicitly forbidding the model from inventing alerts (FR-021). The user-message block contains a bullet list of the currently active alerts (rule name, target, severity, created timestamp, message) plus a small context dump of known device roles and scheduled activities. The model is instructed to respond in ≤3 sentences. The response is returned as plain text in the recommendations API response under an `ai_narrative` key; the frontend renders it in a distinctly styled banner to satisfy FR-019.

---

## 5. Home Assistant delivery: transport and credential handling

**Decision**: The optional Home Assistant integration is a single `NotificationSink` row (`type='home_assistant'`) containing a webhook URL, an enabled flag, and a severity cutoff. The rule engine, at the moment it creates a new `active` alert, checks for an enabled sink whose severity cutoff matches and fires a fire-and-forget async `httpx.post` with a 5-second timeout. Failures are logged with the failing alert ID and swallowed. Credentials (the full webhook URL, which may contain a token) are stored plaintext in the Postgres row (the DB is local, the container is on a private LAN, Constitution I) but the API response returned by `GET /settings/notifications` masks the token portion of the URL.

**Rationale**:
- Webhooks are the standard Home Assistant notification transport and fit the local-only, no-auth-gate model. No REST API key juggling, no OAuth.
- A 5-second timeout keeps the engine loop snappy even if HA is slow or unreachable. Delivery within 30 seconds (SC-007) is easily satisfied since the engine cycle runs every 60 seconds and the HTTP call happens inline.
- Fire-and-forget matches FR-026 ("alert is still recorded locally and the failure is logged without crashing the advisor"). No retry queue — if HA is down, the alert is on the dashboard anyway.
- Credential masking on readback satisfies FR-027. Storing the raw URL in the DB is acceptable because the DB is on a private host in a private LAN; encrypting at rest would require a KMS, which is out of scope per Constitution II.

**Alternatives considered**:
- *Home Assistant REST API with long-lived token*: Rejected. More config surface (token + entity IDs + message template) for the same effect as a webhook.
- *MQTT broker for delivery*: Rejected. Requires a broker, topic conventions, retained-message semantics — way more complexity than a direct POST.
- *Retry queue with exponential backoff*: Rejected. The alert is already persistently recorded in the advisor. Admin sees it on the next dashboard load. A retry queue is complexity without meaningful benefit at single-admin scale.

**Settings UI contract**: On `GET /settings/notifications`, the response returns the webhook host + path with the query string and any `/api/webhook/<secret>` trailing path segment replaced by `***`. On `POST` / `PUT`, the full URL is accepted and stored verbatim. On `PATCH` with a masked URL, the existing URL is kept (the UI can send the masked value to signal "no change").

---

## 6. Unknown-device rule persistence (transient vs. persistent)

**Decision**: The "unknown device on network" rule uses a small rolling window check over the existing device-scanner output (from F4.2's `scan` table). A device is considered *persistent unknown* if it has been seen in at least 3 consecutive scans spanning at least 30 minutes and is not in the inventory's `known` set. Transient devices that appear once and vanish never trigger the rule.

**Rationale**:
- The spec's edge-case list calls out: "A device that appears briefly (e.g., guest phone) should be distinguishable from a device that persists."
- The device scanner already runs periodically and produces scan history (F4.2). We don't need a new data source.
- "3 consecutive scans over 30 minutes" is a conservative default that filters guest phones and captive-portal scanner beacons without waiting so long that a real intruder goes undetected. It is a code-level default, not a user-tunable threshold — keeping the settings page small.

**Alternatives considered**:
- *Fire on first sighting*: Rejected. Guest phones would spam the log.
- *User-tunable window*: Rejected. One more slider on the settings page for a rule 99% of users will leave alone.
- *Require admin to pre-approve a new MAC*: Rejected. That's an enrollment workflow, a whole different feature. The existing inventory + alert is sufficient signal.

---

## 7. Chat context integration (FR-028)

**Decision**: Extend the existing `prompt_assembler.py` from F4.4 to pull active (non-resolved) alerts via a new helper and append them to the system prompt under an `## Active Alerts` heading. Same pattern already used for devices and services. Capped at 20 alerts in the prompt to bound token usage; if more are active, a trailing "(N more not shown)" line is appended.

**Rationale**:
- FR-028 is a one-line requirement — the minimum viable integration is adding an existing DB query into the existing prompt assembler. No new subsystem, no new contract.
- Caps the context to bound Llama 3.1 8B token usage without dropping high-severity alerts: the capping is ordered `critical` → `warning` → `info`, `created_at DESC`.
- No schema changes needed in F4.4's chat feature.

**Alternatives considered**:
- *Inject via retrieval augmentation at chat time*: Rejected. Active alert count is bounded and small; direct injection is simpler.
- *Leave F4.4 unchanged, ship an "alerts context" in v2*: Rejected. The spec explicitly calls out FR-028 in scope; the integration is trivially small.

---

## Summary of resolved decisions

| Decision point | Choice |
|---|---|
| Alert schema | Extend existing `alerts` table via migration 004 |
| Engine host process | Reuse backend FastAPI process; `asyncio` background task alongside `health_checker` |
| Cadence | 60 s, configurable |
| Sustained-breach tracking | In-process dict per `(rule_id, target_id)` |
| Cool-down tracking | DB predicate on `resolved_at` |
| Rule definition | Python modules + static registry |
| AI narrative trigger | Lazy, dashboard-read time, 60 s TTL cache, 10 s Ollama timeout, graceful skip |
| HA transport | Webhook `httpx.post`, 5 s timeout, fire-and-forget, mask on readback |
| Unknown-device rule | 3 consecutive scans across ≥30 minutes |
| Chat context integration | Extend existing `prompt_assembler.py`, cap at 20 active alerts |

All open questions resolved. Ready for Phase 1.
