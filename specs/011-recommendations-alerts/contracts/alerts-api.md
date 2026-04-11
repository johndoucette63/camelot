# API Contract: Recommendations & Alerts

**Feature**: 011-recommendations-alerts
**Base path**: all endpoints live under the existing advisor backend at `http://advisor.holygrail/api` (via Traefik). This document uses paths relative to that base.
**Auth**: LAN-trusted, no auth gate (inherits the existing advisor posture).
**Content type**: `application/json` unless stated otherwise.

This file is the REST contract for all new endpoints added by this feature. Each endpoint lists request shape, success response, error responses, and the functional requirements it satisfies.

---

## Routers

| Router | Path prefix | Owns |
|---|---|---|
| `recommendations` | `/recommendations` | Dashboard panel: currently active alerts + optional AI narrative |
| `alerts` | `/alerts` | Full history log: list, filter, acknowledge, resolve |
| `settings` | `/settings` | Thresholds, active mutes, notification sinks |

---

## 1. Recommendations panel

### `GET /recommendations`

Returns the active recommendations for the dashboard panel, plus an optional AI-generated narrative consolidating them. Backs User Story 1 acceptance scenarios and the FR-003 dashboard panel.

**Query parameters**: none.

**Response 200**:

```json
{
  "active": [
    {
      "id": 1247,
      "rule_id": "pi_cpu_high",
      "rule_name": "Sustained high CPU on Pi",
      "severity": "warning",
      "target_type": "device",
      "target_id": 3,
      "target_label": "torrentbox",
      "message": "torrentbox CPU at 92% for 6 minutes — consider migrating Deluge to HOLYGRAIL",
      "state": "active",
      "source": "rule",
      "created_at": "2026-04-10T14:23:11Z",
      "acknowledged_at": null
    }
  ],
  "counts": {
    "critical": 0,
    "warning": 1,
    "info": 0
  },
  "ai_narrative": {
    "text": "Torrentbox is under sustained load — CPU is at 92% and disk I/O is climbing, which coincides with Sonarr and Radarr import activity. This is not an outage but explains the dashboard-wide slowdown.",
    "generated_at": "2026-04-10T14:23:15Z",
    "source": "ollama"
  }
}
```

- `active`: list of currently-open alerts (`state IN ('active','acknowledged') AND suppressed = false`), ordered by `severity` (critical → warning → info) then `created_at DESC`.
- `counts`: at-a-glance totals by severity (FR-016).
- `ai_narrative`: present only if Ollama successfully returned text within the 10-second budget. If absent or `null`, the frontend MUST render the rule-based list normally (FR-020). When present, the frontend MUST render it with a distinct "AI-assisted" badge (FR-019).

**Observability**: request logs include active alert count, whether narrative was served from cache, and narrative latency.

**Satisfies**: FR-003, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021.

---

## 2. Alert history

### `GET /alerts`

Paginated, filterable list of alert instances for the history log. Backs User Story 3.

**Query parameters**:

| Name | Type | Default | Notes |
|---|---|---|---|
| `severity` | `info` \| `warning` \| `critical` | all | Repeatable: `?severity=warning&severity=critical`. |
| `state` | `active` \| `acknowledged` \| `resolved` | all | Repeatable. |
| `rule_id` | string | — | Filter by rule identifier (e.g. `pi_cpu_high`). For `unknown_device`, accepts either the base `unknown_device` (matches any MAC via prefix match on the `:` separator) or the fully-qualified `unknown_device:aa:bb:cc:dd:ee:ff`. |
| `device_id` | integer | — | Filter by target device. |
| `service_id` | integer | — | Filter by target service. |
| `since` | ISO-8601 timestamp | 30 days ago | Inclusive lower bound on `created_at`. Clamped to the 30-day retention window (FR-015). |
| `until` | ISO-8601 timestamp | now | Inclusive upper bound on `created_at`. |
| `include_suppressed` | boolean | `false` | When `true`, returns suppressed rows too (for audit). |
| `limit` | integer | 100 | Max 500. |
| `offset` | integer | 0 | Standard pagination. |

**Response 200**:

```json
{
  "total": 317,
  "items": [
    {
      "id": 1247,
      "rule_id": "pi_cpu_high",
      "rule_name": "Sustained high CPU on Pi",
      "severity": "warning",
      "target_type": "device",
      "target_id": 3,
      "target_label": "torrentbox",
      "message": "torrentbox CPU at 92% for 6 minutes — consider migrating Deluge to HOLYGRAIL",
      "state": "resolved",
      "source": "rule",
      "suppressed": false,
      "created_at": "2026-04-10T14:23:11Z",
      "acknowledged_at": "2026-04-10T14:24:00Z",
      "resolved_at": "2026-04-10T14:29:18Z",
      "resolution_source": "auto"
    }
  ],
  "limit": 100,
  "offset": 0
}
```

**Response 400** if a filter is malformed (bad ISO timestamp, unknown severity, limit > 500). Body is `{"detail": "..."}`.

**Performance**: served by the `alerts_state_created_at_idx` index; SC-005 target is <2 s for 100 items over thousands of rows.

**Satisfies**: FR-012, FR-013, FR-015, FR-016, SC-004, SC-005.

---

### `POST /alerts/{id}/acknowledge`

Transitions an `active` alert to `acknowledged`. Idempotent: acknowledging an already-acknowledged alert returns 200 with unchanged timestamps.

**Request**: no body.

**Response 200**:

```json
{
  "id": 1247,
  "state": "acknowledged",
  "acknowledged_at": "2026-04-10T14:24:00Z"
}
```

**Response 404** if the alert does not exist.
**Response 409** if the alert is already `resolved` (acknowledging a resolved alert is not allowed per the state machine in data-model.md §3). Body: `{"detail": "cannot acknowledge a resolved alert"}`.

**Satisfies**: FR-014 (part 1).

---

### `POST /alerts/{id}/resolve`

Manually resolves an `active` or `acknowledged` alert. Sets `resolved_at = now()` and `resolution_source = 'manual'`.

**Request**: no body.

**Response 200**:

```json
{
  "id": 1247,
  "state": "resolved",
  "resolved_at": "2026-04-10T14:25:12Z",
  "resolution_source": "manual"
}
```

**Response 404** if the alert does not exist.
**Response 409** if the alert is already `resolved`. Body: `{"detail": "alert already resolved"}`.

**Satisfies**: FR-014 (part 2), FR-005.

---

## 3. Settings — thresholds

### `GET /settings/thresholds`

Returns all configured thresholds for the settings page.

**Response 200**:

```json
{
  "thresholds": [
    {
      "key": "cpu_percent",
      "value": 80,
      "unit": "%",
      "default_value": 80,
      "min_value": 10,
      "max_value": 100,
      "updated_at": "2026-04-10T12:00:00Z"
    },
    {
      "key": "disk_percent",
      "value": 85,
      "unit": "%",
      "default_value": 85,
      "min_value": 10,
      "max_value": 100,
      "updated_at": "2026-04-10T12:00:00Z"
    }
  ]
}
```

**Satisfies**: FR-007, FR-008.

---

### `PUT /settings/thresholds/{key}`

Updates the value of one threshold.

**Request**:

```json
{
  "value": 75
}
```

**Response 200**: the updated threshold row (same shape as the items in `GET /settings/thresholds`).

**Response 400** if `value` is outside `[min_value, max_value]` or non-numeric. Body: `{"detail": "value must be between 10 and 100"}`.

**Response 404** if the `key` is unknown.

**Behavioral note**: the change takes effect on the next engine cycle without a service restart (FR-011). The router simply UPDATEs the row — the engine re-reads the thresholds table at the top of every cycle.

**Satisfies**: FR-008, FR-009, FR-010, FR-011.

---

## 4. Settings — rule mutes

### `GET /settings/mutes`

Returns the list of currently active mutes (not expired, not cancelled).

**Query parameters**:

| Name | Type | Default | Notes |
|---|---|---|---|
| `include_expired` | boolean | `false` | When `true`, includes rows where `expires_at <= now()` or `cancelled_at IS NOT NULL`. Used by the "mute history" view. |

**Response 200**:

```json
{
  "mutes": [
    {
      "id": 42,
      "rule_id": "pi_cpu_high",
      "rule_name": "Sustained high CPU on Pi",
      "target_type": "device",
      "target_id": 3,
      "target_label": "torrentbox",
      "created_at": "2026-04-10T13:00:00Z",
      "expires_at": "2026-04-10T17:00:00Z",
      "remaining_seconds": 13420,
      "note": "Known heavy import; quiet until tonight"
    }
  ]
}
```

**Satisfies**: FR-011c.

---

### `POST /settings/mutes`

Creates a new mute.

**Request**:

```json
{
  "rule_id": "pi_cpu_high",
  "target_type": "device",
  "target_id": 3,
  "duration_seconds": 14400,
  "note": "Known heavy import; quiet until tonight"
}
```

- `duration_seconds` is required and must be > 0 and ≤ 86400 × 7 (7 days maximum to prevent permanent silent muting).
- `target_id` required when `target_type` is `device` or `service`; forbidden when `target_type='system'`.

**Response 201**: same shape as a single `mutes` row.

**Response 400** on invalid duration, unknown `rule_id`, or target mismatch. Body: `{"detail": "..."}`.

**Satisfies**: FR-011a.

---

### `DELETE /settings/mutes/{id}`

Cancels an active mute early (FR-011c). Idempotent on an already-cancelled or expired mute: returns 204 either way.

**Response 204**: no body.

**Satisfies**: FR-011c.

---

## 5. Settings — notification sinks (Home Assistant)

### `GET /settings/notifications`

Returns the configured notification sinks. The `endpoint` field is masked — any token-like path segment (`/api/webhook/<secret>`) or query-string token is replaced with `***` before returning.

**Response 200**:

```json
{
  "sinks": [
    {
      "id": 1,
      "type": "home_assistant",
      "name": "Home Assistant on HOLYGRAIL",
      "enabled": true,
      "endpoint_masked": "http://homeassistant.holygrail/api/webhook/***",
      "min_severity": "critical",
      "created_at": "2026-04-05T09:00:00Z",
      "updated_at": "2026-04-10T12:00:00Z"
    }
  ]
}
```

**Satisfies**: FR-022, FR-023, FR-027.

---

### `PUT /settings/notifications/{id}`

Updates a sink. Accepts any subset of fields. If `endpoint` is omitted, the existing stored URL is preserved (used by the frontend to save other field changes without re-sending a masked URL).

**Request**:

```json
{
  "enabled": true,
  "min_severity": "warning",
  "endpoint": "http://homeassistant.holygrail/api/webhook/new-secret-token"
}
```

**Response 200**: masked sink, same shape as `GET`.

**Response 400** on invalid URL, invalid severity, or unknown sink id.

**Behavioral note**: toggling `enabled` takes effect on the next alert created by the engine — no restart required (FR-025).

**Satisfies**: FR-023, FR-024, FR-025, FR-027.

---

### `POST /settings/notifications/{id}/test`

Sends a synthetic test alert through the sink so the admin can verify Home Assistant receives it. Does NOT create a row in `alerts`.

**Request**: no body.

**Response 200** on successful delivery:

```json
{
  "ok": true,
  "status_code": 200,
  "latency_ms": 47
}
```

**Response 502** on delivery failure:

```json
{
  "ok": false,
  "error": "connection refused"
}
```

**Satisfies**: FR-025 (user can verify the toggle works), supports SC-007.

---

## 6. Engine-internal observability

Not exposed as a public endpoint in v1. The engine logs structured JSON lines to stdout via the existing logger:

- `rule_engine.cycle.started` — begins each cycle.
- `rule_engine.cycle.completed` — fields: `duration_ms`, `rules_evaluated`, `alerts_created`, `alerts_resolved`, `alerts_suppressed`, `ha_notifications_sent`, `ha_notifications_failed`.
- `rule_engine.rule.error` — a rule raised an exception; includes `rule_id`, `exception`, stack trace.
- `rule_engine.ha.delivery_failed` — fields: `sink_id`, `alert_id`, `error`.
- `ai_narrative.call.ok` / `ai_narrative.call.failed` — fields: `latency_ms`, `alert_count`, `error`.

Grafana dashboards are out of scope for v1 (Constitution II — YAGNI for a single admin).

---

## 7. Error shape

All error responses follow the FastAPI default:

```json
{"detail": "human-readable message"}
```

Consistent with every other existing advisor endpoint.
