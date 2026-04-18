# REST Contract — Home Assistant Integration

**Feature**: 016-ha-integration
**Scope**: New endpoints under `/settings/home-assistant`, `/ha/entities`, `/ha/thread`, plus extensions to the existing `/settings/notification-sinks` endpoint.

All endpoints are served by the advisor FastAPI backend at its existing base URL (`http://advisor.holygrail` via Traefik, or `http://localhost:8000` during development). Authentication matches the rest of the advisor app — LAN-trusted, no bearer tokens on these internal endpoints. Access tokens in request bodies are never echoed back in any response.

---

## 1. Connection management

### `GET /settings/home-assistant`

Read the current HA connection config (redacted).

**Response 200**:

```json
{
  "configured": true,
  "base_url": "http://homeassistant.local:8123",
  "token_masked": "lllat_…WXYZ",
  "status": "ok",
  "last_success_at": "2026-04-17T14:03:12Z",
  "last_error": null,
  "last_error_at": null
}
```

When `configured` is `false`, all other fields are `null`. `status` is one of `ok`, `auth_failure`, `unreachable`, `unexpected_payload`, `not_configured`. `token_masked` shows the last 4 characters only; the full token is never returned.

### `PUT /settings/home-assistant`

Save or replace the connection. Validates by calling HA's `/api/` root endpoint before persisting.

**Request**:

```json
{
  "base_url": "http://homeassistant.local:8123",
  "access_token": "llat_<full long-lived access token>"
}
```

**Response 200** (on successful validation + save): same shape as the GET response above, with `status = "ok"`.

**Response 400**:

```json
{
  "status": "auth_failure",
  "detail": "Home Assistant rejected the token (HTTP 401)."
}
```

Classes: `auth_failure`, `unreachable`, `unexpected_payload`, `invalid_url`. On any non-`ok` outcome the connection is **not** persisted; the admin must correct and retry.

### `POST /settings/home-assistant/test-connection`

Live validation without saving. Used by the UI's "Test Connection" button before the admin commits.

**Request**: same as PUT.
**Response**: same shape as PUT's 200 / 400, but nothing is persisted.

### `DELETE /settings/home-assistant`

Remove the connection. The poller stops within one cycle (FR-004). Existing HA-sourced inventory rows retain their `ha_device_id` values but `ha_last_seen_at` stops advancing; they fall through the existing stale-device pipeline (FR-029). HA-variant notification sinks become inactive (`delivery_status='n/a'` for new alerts, no dispatch).

**Response 204**.

---

## 2. Entity snapshot (for the HA dashboard tab)

### `GET /ha/entities`

Return the current snapshot. Supports simple filtering/sorting.

**Query params**:
- `domain` — optional, repeatable; filters to matching HA domains.
- `search` — optional substring match against `friendly_name` or `entity_id`.
- `stale_only` — optional boolean; when `true`, returns entities whose `last_changed` is older than 1 h.

**Response 200**:

```json
{
  "connection_status": "ok",
  "polled_at": "2026-04-17T14:03:12Z",
  "stale": false,
  "entities": [
    {
      "entity_id": "binary_sensor.front_door_open",
      "ha_device_id": "abcd1234-…",
      "domain": "binary_sensor",
      "friendly_name": "Front Door Open",
      "state": "off",
      "last_changed": "2026-04-17T09:14:02Z",
      "attributes": { "device_class": "opening", "battery_level": 87 }
    }
  ]
}
```

When HA is currently unreachable, `stale` is `true` and `entities` contains the last successful snapshot (FR-008).

---

## 3. Thread view

### `GET /ha/thread`

Return the derived Thread topology.

**Response 200**:

```json
{
  "connection_status": "ok",
  "polled_at": "2026-04-17T14:03:12Z",
  "border_routers": [
    {
      "ha_device_id": "br-1",
      "friendly_name": "HomePod mini – Kitchen",
      "model": "HomePod mini",
      "online": true,
      "attached_device_count": 7
    }
  ],
  "devices": [
    {
      "ha_device_id": "dev-42",
      "friendly_name": "Aqara Motion — Hallway",
      "parent_border_router_id": "br-1",
      "online": true,
      "last_seen_parent_id": "br-1"
    }
  ],
  "orphaned_device_count": 0
}
```

**Empty-state response** — when HA exposes no Thread data (FR-013):

```json
{
  "connection_status": "ok",
  "polled_at": "2026-04-17T14:03:12Z",
  "border_routers": [],
  "devices": [],
  "orphaned_device_count": 0,
  "empty_reason": "no_thread_integration_data"
}
```

---

## 4. Notification-sink extension

The existing `/settings/notification-sinks` endpoint from 011-recommendations-alerts is extended to accept a new `type` value.

### `POST /settings/notification-sinks` (new variant)

```json
{
  "type": "home_assistant",
  "name": "Phone (HA push)",
  "enabled": true,
  "endpoint": "mobile_app_pixel9",
  "min_severity": "critical"
}
```

- `endpoint` for this variant holds the HA `notify.*` service name, not a URL.
- `min_severity` defaults to `critical` per FR-017.
- The server resolves the HA base URL and bearer token from the singleton connection; 400 is returned if no HA connection is configured.

Other sink types (`webhook`, etc.) from 011 are unchanged.

### `GET /settings/notification-sinks/available-ha-services`

Returns the list of `notify.*` service names the current HA instance exposes, so the UI can populate the dropdown on the sink form.

**Response 200**:

```json
{
  "services": ["mobile_app_pixel9", "mobile_app_ipad", "persistent_notification"]
}
```

Returns `409` with `{ "detail": "Home Assistant is not currently reachable" }` when HA is down; the UI then falls back to free-text entry.

---

## 5. Error shapes (common)

All 4xx and 5xx responses use FastAPI's default shape:

```json
{ "detail": "<human message>" }
```

Classification codes (used in the UI to pick copy) appear in structured responses as documented above (`status`, `empty_reason`). Error codes never leak the decrypted access token, the ciphertext, or the encryption key.

---

## 6. Out-of-scope (v1)

- No GET/PUT for individual entity snapshots — the snapshot is refreshed as a whole by the poller.
- No POST to trigger an immediate poll — the 60 s cadence is fast enough for the feature's use cases, and ad-hoc forcing would complicate the retry/backoff state.
- No write endpoints to Home Assistant (the advisor does not toggle entities, call non-notify services, or push state — the integration is read + notify only).
- No multi-HA support — `PUT /settings/home-assistant` replaces the single connection.
