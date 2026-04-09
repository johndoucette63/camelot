# REST API Contract: Network Discovery & Device Inventory

**Feature**: 008-network-discovery-inventory  
**Base URL**: `/api/` (proxied by nginx frontend → backend:8000)  
**Date**: 2026-04-09

---

## Devices

### `GET /api/devices`

Returns all devices in the inventory.

**Query parameters**:
- `online` (bool, optional) — filter by online/offline status
- `sort` (string, optional) — field to sort by: `ip`, `hostname`, `mac`, `vendor`, `last_seen` (default: `ip`)
- `order` (string, optional) — `asc` | `desc` (default: `asc`)
- `q` (string, optional) — filter by hostname or IP (substring match)

**Response 200**:
```json
[
  {
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "ip_address": "192.168.10.129",
    "hostname": "HOLYGRAIL",
    "vendor": "ASRock Incorporation",
    "first_seen": "2026-04-09T12:00:00Z",
    "last_seen": "2026-04-09T14:00:00Z",
    "is_online": true,
    "is_known_device": true,
    "annotation": {
      "role": "server",
      "description": "Ryzen 7800X3D — central server",
      "tags": ["plex", "ollama", "monitoring"]
    }
  }
]
```

---

### `GET /api/devices/{mac_address}`

Returns a single device by MAC address. MAC in URL must be URL-encoded if needed (`:` is safe in path segments).

**Response 200**: Single device object (same shape as list item above).  
**Response 404**: `{"detail": "Device not found"}`

---

### `PATCH /api/devices/{mac_address}/annotation`

Update the annotation for a device. All fields are optional; omitted fields are unchanged.

**Request body**:
```json
{
  "role": "server",
  "description": "Ryzen 7800X3D — central server",
  "tags": ["plex", "ollama"]
}
```

**Valid roles**: `server`, `workstation`, `iot`, `storage`, `networking`, `printer`, `dns`, `unknown`

**Response 200**: Updated device object (same shape as GET /api/devices/{mac}).  
**Response 404**: `{"detail": "Device not found"}`  
**Response 422**: Validation error (invalid role value, etc.)

---

## Events

### `GET /api/events`

Returns event history (max 30 days retention).

**Query parameters**:
- `type` (string, optional) — filter by event type: `new-device`, `offline`, `back-online`, `scan-error`
- `since` (ISO 8601 datetime, optional) — only events after this time (default: last 24 hours for AI context use)
- `limit` (int, optional) — max results to return (default: 100, max: 500)
- `offset` (int, optional) — pagination offset (default: 0)

**Response 200**:
```json
{
  "total": 42,
  "events": [
    {
      "id": 17,
      "event_type": "new-device",
      "timestamp": "2026-04-09T13:45:00Z",
      "device": {
        "mac_address": "11:22:33:44:55:66",
        "ip_address": "192.168.10.201",
        "hostname": null,
        "vendor": "Espressif Inc."
      },
      "details": {}
    },
    {
      "id": 16,
      "event_type": "scan-error",
      "timestamp": "2026-04-09T13:30:00Z",
      "device": null,
      "details": {
        "error": "nmap process timed out after 300 seconds"
      }
    }
  ]
}
```

---

## Scans

### `GET /api/scans`

Returns recent scan history.

**Query parameters**:
- `limit` (int, optional) — max results (default: 20, max: 100)

**Response 200**:
```json
[
  {
    "id": 5,
    "started_at": "2026-04-09T14:00:00Z",
    "completed_at": "2026-04-09T14:02:31Z",
    "status": "completed",
    "devices_found": 12,
    "new_devices": 0,
    "error_detail": null
  }
]
```

---

### `POST /api/scans/trigger`

Manually trigger an immediate scan outside the scheduled interval.

**Request body**: (empty)

**Response 202**: Scan accepted and queued.
```json
{"message": "Scan triggered"}
```

**Response 409**: A scan is already in progress.
```json
{"detail": "Scan already running"}
```

---

## Health (existing, unchanged)

### `GET /api/health`

**Response 200**: `{"status": "ok"}`

---

## Error Responses

All error responses follow FastAPI's default format:
```json
{"detail": "Human-readable error message"}
```

HTTP status codes used:
- `200` — success
- `202` — accepted (async operation started)
- `404` — resource not found
- `409` — conflict (duplicate operation)
- `422` — validation error
- `500` — unexpected server error
