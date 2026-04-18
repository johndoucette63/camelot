# Data Model — Home Assistant Integration

**Feature**: 016-ha-integration
**Migration**: `advisor/backend/migrations/versions/008_home_assistant_integration.py`

---

## New tables

### `home_assistant_connections`

Singleton — the migration seeds one row at `id=1` and the application enforces singleton semantics in code. A deleted connection is represented by `base_url IS NULL` rather than a deleted row, so pre-existing sink FKs stay valid.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `integer` PK | Always `1`. |
| `base_url` | `text NULL` | e.g. `http://homeassistant.local:8123`. `NULL` means "not configured". |
| `token_ciphertext` | `bytea NULL` | Fernet ciphertext of the long-lived access token. `NULL` iff `base_url` is `NULL`. |
| `last_success_at` | `timestamptz NULL` | Last successful `/api/states` fetch. |
| `last_error` | `text NULL` | Class from R8 (`auth_failure`, `unreachable`, `unexpected_payload`) plus a short human message. |
| `last_error_at` | `timestamptz NULL` | When the current error started. |
| `created_at` / `updated_at` | `timestamptz NOT NULL` | Standard audit. |

### `ha_entity_snapshots`

The filtered entity set from the most recent poll. Upserted in place on every cycle. Entities that disappear from HA are deleted from this table at the end of the cycle (unless they reappear within the same cycle, in which case they're upserted).

| Column | Type | Notes |
|--------|------|-------|
| `entity_id` | `text PK` | HA entity ID (e.g., `binary_sensor.front_door_open`). |
| `ha_device_id` | `text NOT NULL` | HA per-device UUID. Indexed. |
| `domain` | `text NOT NULL` | Derived from the prefix of `entity_id`. |
| `friendly_name` | `text NOT NULL` | |
| `state` | `text NOT NULL` | HA's reported state string. |
| `last_changed` | `timestamptz NOT NULL` | From HA. |
| `attributes` | `jsonb NOT NULL` | Small attribute projection (e.g., `battery_level`, `device_class`, `signal_strength`). |
| `polled_at` | `timestamptz NOT NULL` | Advisor-side timestamp; equals the cycle's start. |

Indexes: `(ha_device_id)`, `(domain)`, `(last_changed DESC)`.

### `thread_border_routers`

Derived from the `/api/config/thread/status` diagnostic blob + entities with integration `thread`. Rebuilt each cycle from the authoritative HA view.

| Column | Type | Notes |
|--------|------|-------|
| `ha_device_id` | `text PK` | HA device UUID of the border router. |
| `friendly_name` | `text NOT NULL` | |
| `model` | `text NULL` | Manufacturer/model string if HA exposes it. |
| `online` | `boolean NOT NULL` | |
| `attached_device_count` | `integer NOT NULL` | Derived from the Thread status blob. |
| `last_refreshed_at` | `timestamptz NOT NULL` | |

### `thread_devices`

Derived. Same lifecycle rules as `thread_border_routers`.

| Column | Type | Notes |
|--------|------|-------|
| `ha_device_id` | `text PK` | |
| `friendly_name` | `text NOT NULL` | |
| `parent_border_router_id` | `text NULL` | FK → `thread_border_routers.ha_device_id` ON DELETE SET NULL. Null means the device is orphaned or its parent hasn't reported yet. |
| `online` | `boolean NOT NULL` | |
| `last_seen_parent_id` | `text NULL` | Preserved across refreshes so the UI can say "last connected via X" even after the device drops off. |
| `last_refreshed_at` | `timestamptz NOT NULL` | |

---

## Modified tables

### `devices` (extended from 008-network-discovery-inventory / 013-device-enrichment)

New columns:

| Column | Type | Notes |
|--------|------|-------|
| `ha_device_id` | `text NULL UNIQUE` | Canonical link back to HA (clarification Q1). Unique index, partial on non-null. |
| `ha_connectivity_type` | `text NULL` | One of `lan_wifi`, `lan_ethernet`, `thread`, `zigbee`, `other`. Reported to the UI. |
| `ha_last_seen_at` | `timestamptz NULL` | Last time the device appeared in an HA poll. |

Altered columns / constraints:

| Change | Rationale |
|--------|-----------|
| `mac_address` becomes nullable | Thread/Zigbee endpoints don't have a LAN MAC. |
| Drop `UNIQUE(mac_address)`, replace with `CREATE UNIQUE INDEX devices_mac_address_unique ON devices (mac_address) WHERE mac_address IS NOT NULL` | Preserves dedup for scanner-discovered rows without forcing MACs on HA-only rows. |
| Add `CHECK (mac_address IS NOT NULL OR ha_device_id IS NOT NULL)` | Prevents anonymous rows. |

### `notification_sinks` (extended from 011-recommendations-alerts)

New column:

| Column | Type | Notes |
|--------|------|-------|
| `home_assistant_id` | `integer NULL` FK → `home_assistant_connections(id)` ON DELETE SET NULL | Populated only when `type = 'home_assistant'`. |

Existing columns keep their meaning; for `type = 'home_assistant'` the existing `endpoint` column holds the HA notify service name (e.g., `mobile_app_pixel9`), and `home_assistant_id` references the singleton connection so the dispatcher can read the bearer token.

### `alerts` (extended from 011-recommendations-alerts)

New columns to support the retry-budget state machine (R6):

| Column | Type | Notes |
|--------|------|-------|
| `delivery_status` | `text NOT NULL DEFAULT 'pending'` | One of `pending`, `sent`, `failed`, `suppressed`, `terminal`, `n/a`. `n/a` means "no forwarding configured". |
| `delivery_attempt_count` | `integer NOT NULL DEFAULT 0` | |
| `delivery_last_attempt_at` | `timestamptz NULL` | |
| `delivery_next_attempt_at` | `timestamptz NULL` | Driven by R6's backoff table; `NULL` when no retry is scheduled. |

Existing columns (`rule_id`, `target_type`, `target_id`, etc.) are unchanged.

---

## State transitions

### HA connection health

```
┌──────────────┐  save+validate OK   ┌──────┐
│ not_configured ├───────────────────▶│  ok  │
└──────┬───────┘                      └───┬──┘
       │                                  │ auth_failure
       │                                  ▼
       │                          ┌────────────────┐
       │                          │ auth_failure   │──▶ critical recommendation (FR-024)
       │                          └────────────────┘
       │                                  │ admin-saves-new-token
       │                                  ▼
       │                                  ok
       │                                  │ connection error / timeout
       │                                  ▼
       │                          ┌────────────────┐
       │                          │ unreachable    │──▶ warning recommendation (FR-023)
       │                          └────────────────┘
       │                                  │ auto-resume
       │                                  ▼
       │                                  ok
       │
       │ admin deletes connection
       ▼
┌──────────────┐
│ not_configured│
└──────────────┘
```

### Outbound notification delivery (per alert)

```
pending ──send ok──▶ sent
   │
   ├─ send 5xx/timeout, attempts < 4 ──▶ failed (schedule next: 30/60/120 s)
   │       ▲
   │       │ retry loop
   │       │
   └─ send 5xx/timeout, attempts == 4 ──▶ terminal (raise recommendation)
   
pending ──matches mute ──▶ suppressed
pending ──severity < threshold ──▶ n/a (recorded but not forwarded)
```

### Thread border-router online/offline (for new rule)

A transition from `online=true` on poll N−1 to `online=false` on poll N for the same `ha_device_id` triggers rule `thread_border_router_offline`, which creates an alert keyed by `(rule_id='thread_border_router_offline', target_type='ha_device', target_id=<id hash or FK-less int>)`. Resolution is condition-driven on the next transition back to `online=true`. The existing dedup/mute/cool-down semantics from 011 apply unchanged.

---

## Entity relationships

```
HomeAssistantConnection (1, singleton)
    │
    │ 1..1
    │
    ├────────── NotificationSink (0..N, when type='home_assistant')
    │
    │ feeds
    ▼
HAEntitySnapshot (0..N) ─────── joined by ha_device_id ──────► Device (0..N)
    │
    │ refresh derives
    ▼
ThreadBorderRouter (0..N) ◀─ parent_border_router_id ── ThreadDevice (0..N)
```

`Alert` gains delivery columns but keeps its existing relationships to `Device` and `Service`.
