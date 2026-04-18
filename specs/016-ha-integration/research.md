# Research — Home Assistant Integration

**Feature**: 016-ha-integration
**Date**: 2026-04-17
**Purpose**: Resolve technical unknowns before Phase 1 design. All items answered; no `NEEDS CLARIFICATION` remains.

---

## R1 — HA API style: REST polling vs. WebSocket subscription

**Decision**: REST polling on a configurable interval (default 60 s).

**Rationale**: The spec's Assumptions explicitly defer real-time streaming; clarification Q3 pinned the notification retry budget to 5 min of exponential backoff, which implicitly assumes a polling / request-response interaction model. REST polling is trivial to implement with the existing `httpx` dependency, is naturally idempotent, and fits a single-home fleet of ≤200 curated entities without straining HA. A WebSocket subscription is a future enhancement when the curated entity set grows or when sub-60-second latency becomes a real requirement.

**Alternatives considered**:
- **HA WebSocket API (`/api/websocket`)** — lower latency, push semantics. Rejected: adds a persistent connection to manage, reconnect/backoff logic grows, and HA-upgrade-window handling becomes more complex than the 5-minute retry spec can express.
- **HA Server-Sent Events** — not a first-class HA capability.

---

## R2 — Entity-domain filter (what to ingest)

**Decision**: Curated built-in allowlist of these HA domains / device classes:
- `device_tracker` (all) — captures Thread border routers and network-attached devices.
- `binary_sensor` with `device_class in ("connectivity", "problem", "running", "update")` — captures online/offline signals.
- `sensor` with `device_class in ("signal_strength", "battery", "temperature", "humidity")` — captures diagnostic readings the admin cares about.
- `switch` and `update` domains (whole-domain) — captures power toggles and HA update availability.
- Any entity whose integration source is `thread` (all domains) — captures Thread metadata regardless of domain shape.

**Rationale**: The spec narrows ingestion to entities relevant to infrastructure monitoring (FR-006). The source brief explicitly mentioned border routers, network devices, and sensors. This curated list captures those without pulling the entire HA entity universe (which in a non-trivial HA install can be thousands of entities — lights, scenes, automations, media players). An admin-managed allowlist UI is out of scope for v1 per Assumptions.

**Alternatives considered**:
- **Ingest everything** — rejected, explodes the snapshot table, mostly noise.
- **Admin allowlist from day one** — rejected per Assumptions; premature configuration surface.

---

## R3 — Thread topology data source in Home Assistant

**Decision**: Use two complementary HA surfaces.
1. `GET /api/states` filtered to entities whose integration source is `thread` — gives per-entity state (border router online, device connectivity).
2. `GET /api/config/thread/status` — gives the router-of-last-resort JSON blob that contains border-router → attached-device mapping, including RLOC16, link quality, and parent-router identity.

**Rationale**: HA's `thread` integration models border routers as device registry entries and exposes limited state through entities, but the parentage graph (which device is attached to which border router) is only available in aggregate form through the diagnostic `thread/status` endpoint. Using both means the advisor can answer "which devices just lost their parent?" — the exact question Story 2 AC-2 needs.

**Alternatives considered**:
- **Entities only** — insufficient for parentage.
- **Diagnostic endpoint only** — no per-entity last-changed timestamps, no other domain coverage.
- **Scrape HA UI pages** — brittle, rejected.

**Note**: The advisor's role is to *surface* HA's view of Thread reality (spec edge case). It does not independently validate that a border router HA reports as online actually works.

---

## R4 — Access-token encryption at rest

**Decision**: Python `cryptography.fernet.Fernet` with a 32-byte URL-safe base64 key supplied via the `ADVISOR_ENCRYPTION_KEY` environment variable on the advisor host. The key is generated once with `Fernet.generate_key()` and persisted into the gitignored `advisor/.env`. The migration stores `token_ciphertext` as `BYTEA`.

**Rationale**: Clarification Q2 selected "symmetric-encrypted in DB with env-var key". Fernet is the standard-library-blessed, versioned construction (AES-128-CBC + HMAC-SHA256 + timestamp) — correctly using AES-GCM by hand is easy to get wrong; Fernet removes the footgun. `cryptography` is a widely-used, permissive-licensed package with prebuilt wheels for the advisor's x86_64 Python 3.12 base image. The env-var pathway matches how PIA credentials are handled in 015-vpn-sidecar, keeping the secret model uniform.

**Alternatives considered**:
- **Raw `cryptography.hazmat.primitives.aead.AESGCM`** — rejected, more rope than the task needs.
- **Postgres pgcrypto `pgp_sym_encrypt`** — moves the secret into DB-level function calls and mixes the key management across Python and SQL; rejected for simplicity.
- **HashiCorp Vault or an external KMS** — scope violation (Constitution I, III); no external services.

**Rotation**: The admin can change `ADVISOR_ENCRYPTION_KEY` only in tandem with re-saving the HA connection (since the old ciphertext is unreadable without the old key). Document this in the quickstart and in `INFRASTRUCTURE.md`.

---

## R5 — Relaxing `devices.mac_address` from `NOT NULL UNIQUE`

**Decision**: Drop the existing `NOT NULL` constraint and the table-level `UNIQUE(mac_address)` constraint. Create a partial unique index `CREATE UNIQUE INDEX devices_mac_address_unique ON devices (mac_address) WHERE mac_address IS NOT NULL;`. Add a `CHECK` constraint that at least one of `mac_address` or `ha_device_id` is non-null so no row is anonymous.

**Rationale**: Spec FR-028 requires Thread/Zigbee endpoints to live in the unified `devices` table, and those endpoints have no MAC. Keeping `mac_address` as the natural identifier for LAN-present devices (all existing rows) while allowing HA-only rows to omit it preserves the existing inventory pipeline behavior without a schema split. Partial unique index preserves the dedup guarantee for scanner-discovered devices (which all have MACs). The CHECK constraint prevents a row with neither a MAC nor an `ha_device_id` from ever appearing, which would be a bug signaler.

**Alternatives considered**:
- **Fake MAC like `HA:<device_id>`** — rejected, pollutes the column, breaks any downstream code that assumes `mac_address` is a real MAC.
- **Separate `ha_devices` table with a FK into `devices`** — rejected, splits the inventory UI and contradicts clarification Q1 (merge fully).
- **Keep NOT NULL, require MAC for HA-only rows** — rejected, HA doesn't know the MAC of a Thread endpoint.

---

## R6 — Retry-budget state machine for notification forwarding

**Decision**: Hold retry state on the `alerts` row via four new columns — `delivery_status` (`pending`, `sent`, `failed`, `suppressed`, `terminal`), `delivery_attempt_count`, `delivery_last_attempt_at`, `delivery_next_attempt_at`. The existing `ha_poller.py` (or a sibling tick in `rule_engine.py`) sweeps on each cycle for rows where `delivery_next_attempt_at <= now()` and replays the send. On success → `sent`. On 5xx/timeout → schedule next attempt per the exponential backoff table below. After 4 attempts (cumulative ~5 min wall clock) → `terminal`, and a recommendation is created.

**Backoff table**:

| Attempt | Delay after previous failure |
|---------|------------------------------|
| 1 (initial) | 0 s — sent immediately on alert creation |
| 2 | 30 s |
| 3 | 60 s |
| 4 | 120 s |
| (terminal) | after 240 s on attempt 4 → recommendation |

Total wall clock to terminal: ~5 min.

**Rationale**: Clarification Q3 pinned the 5-minute exponential-backoff budget. Keeping retry state on the alert row avoids introducing a new table just for delivery attempts and matches constitution II (simplicity). The existing background-loop infrastructure in the advisor already runs every 60 s for health checks, so piggybacking a delivery sweep onto that cadence costs nothing. If the loop cadence ever drops below 30 s, the backoff stays correct; if it rises above 60 s, delivery latency drifts slightly — acceptable for a non-realtime integration.

**Alternatives considered**:
- **`delivery_attempts` log table** — rejected, no reporting requirement justifies the extra table.
- **Celery / RQ with Redis** — rejected outright, Constitution II + no Redis in the stack.
- **`asyncio.sleep` chain inside the sender coroutine** — rejected, would not survive a process restart.

---

## R7 — Notification-service dispatch to Home Assistant

**Decision**: The advisor POSTs to `POST {base_url}/api/services/notify/{service_name}` with:

```http
Authorization: Bearer {decrypted token}
Content-Type: application/json

{
  "title": "...",
  "message": "...",
  "data": {
    "severity": "critical",
    "rule_id": "thread_border_router_offline",
    "target_type": "device",
    "target_id": 42,
    "alert_id": 1234
  }
}
```

The `service_name` is stored on the `NotificationSink` row (e.g., `mobile_app_pixel9`), chosen by the admin from what HA exposes. A `GET /api/services` call during the sink-configuration flow lets the advisor list available `notify.*` services for the admin to pick from.

**Rationale**: This is HA's native notify pathway — `notify.mobile_app_<device>` is exactly what the HA companion app on the admin's phone listens for. No webhook configuration is required on the HA side, no automation setup. The `data` dict is opaque to HA but gets passed through to the Android/iOS companion app where the admin can write a simple mobile automation if they want channel/priority tweaks.

**Alternatives considered**:
- **HA webhooks (POST to a `/api/webhook/<id>` the admin configures)** — rejected, requires the admin to set up a matching HA automation; the existing F4.5 webhook sink already covers that use case for admins who prefer it.
- **HA WebSocket API `call_service`** — rejected for the same reason as R1; REST is simpler and fits the retry-state model in R6.

---

## R8 — HA REST error-class handling

**Decision**: Classify HA REST responses into four explicit states that the UI surfaces distinctly (per spec edge case "connection failed vs authentication failed vs unexpected payload"):

| Class | Trigger | UI state | Recommendation raised |
|-------|---------|----------|-----------------------|
| `ok` | 2xx with expected JSON | green | no |
| `auth_failure` | 401 / 403 | "Authentication failed" | yes — critical (FR-024) |
| `unreachable` | connection error, DNS failure, timeout | "Unreachable" (stale snapshot shown) | yes — warning (FR-023) |
| `unexpected_payload` | 2xx with non-JSON body or schema mismatch | "Unexpected response" (likely reverse-proxy issue) | yes — warning |

**Rationale**: The spec edge case calls out these three failure modes as requiring distinct messaging so the admin fixes the right thing. The table above is small enough to encode directly in `ha_client.py`'s response handler.

**Alternatives considered**: Catch-all "connection failed" banner — rejected, not actionable.

---

## R9 — AI chat grounding: how HA snapshot joins the prompt

**Decision**: Extend the existing `prompt_assembler.py` (built in 010-ai-advisor-chat and extended in 011-recommendations-alerts) to include, for chat turns whose classifier tags suggest an IoT/Thread/home-automation question:
1. A compact summary of the HA connection health (last-successful-poll age, current error if any).
2. Counts: total entities in snapshot, online border routers / total border routers, online Thread devices / total Thread devices.
3. Up to 20 recently-changed entities (most-recently-changed first), with entity_id, friendly name, state, last_changed.

**Rationale**: The existing pattern already blends inventory, service registry, and alerts into chat grounding. HA snapshot is a parallel data source. Keep the summary compact — the full snapshot can be thousands of rows on a rich HA install, which would blow the prompt budget and dilute relevance. Classifier-driven inclusion (only for IoT-related questions) prevents polluting unrelated conversations.

**Alternatives considered**: Always include full HA snapshot — rejected, prompt budget + relevance dilution.

---

## R10 — Configuration and env-var surface

**Decision**: Add exactly these new env vars to `advisor/.env.example` and `advisor/backend/app/config.py`:

| Env var | Purpose | Default |
|---------|---------|---------|
| `ADVISOR_ENCRYPTION_KEY` | Fernet key for token encryption at rest | (no default — service refuses to start if unset) |
| `HA_POLL_INTERVAL_SECONDS` | Poll cadence | `60` |
| `HA_REQUEST_TIMEOUT_SECONDS` | Per-request HTTP timeout | `10` |
| `HA_NOTIFY_RETRY_BUDGET_SECONDS` | Wall-clock ceiling for retry loop (R6) | `300` |

Everything else (base URL, access token, notification service target) lives in the DB.

**Rationale**: Matches the existing convention where tunables live in `config.py` but secrets and operational state live in the DB. The one non-optional env var (`ADVISOR_ENCRYPTION_KEY`) fails loudly at startup — Constitution V "silent failures unacceptable".

---

## Summary table

| ID | Area | Decision |
|----|------|----------|
| R1 | API style | REST polling |
| R2 | Entity filter | Curated allowlist (device_tracker, select binary_sensor/sensor, switch, update, thread) |
| R3 | Thread source | `/api/states` + `/api/config/thread/status` |
| R4 | Token encryption | Fernet w/ env-var key |
| R5 | MAC nullability | Nullable + partial unique index + non-null-either CHECK |
| R6 | Retry state | Columns on `alerts` + poller-driven sweep |
| R7 | HA notify call | `POST /api/services/notify/<service>` native, not webhook |
| R8 | Error classes | ok / auth_failure / unreachable / unexpected_payload |
| R9 | AI chat grounding | Compact HA summary included when classifier tags IoT |
| R10 | Env surface | 4 new vars; secrets stay in DB |
