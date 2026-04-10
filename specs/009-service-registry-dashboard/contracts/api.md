# API Contracts: Service Registry & Health Dashboard

**Branch**: `009-service-registry-dashboard`  
**Date**: 2026-04-09  
**Base URL**: `/api` (proxied by Nginx frontend → backend:8000)

---

## New Endpoints

### `GET /services`

Returns all enabled service definitions with their latest health check result.

**Response `200 OK`**:
```json
[
  {
    "id": 1,
    "name": "Plex",
    "host_label": "HOLYGRAIL",
    "host": "192.168.10.129",
    "port": 32400,
    "check_type": "http",
    "enabled": true,
    "latest": {
      "status": "green",
      "checked_at": "2026-04-09T14:32:00Z",
      "response_time_ms": 45,
      "error": null
    }
  },
  {
    "id": 2,
    "name": "Deluge",
    "host_label": "Torrentbox",
    "host": "192.168.10.141",
    "port": 8112,
    "check_type": "http",
    "enabled": true,
    "latest": {
      "status": "red",
      "checked_at": "2026-04-09T14:32:00Z",
      "response_time_ms": null,
      "error": "Connection refused"
    }
  }
]
```

`latest` is `null` if no check has run yet for a service.

---

### `GET /services/{id}/history`

Returns health check history for a single service. Default: last 24 hours. Max: 7 days.

**Query parameters**:
- `hours` (int, optional, default `24`, max `168`) — lookback window in hours

**Response `200 OK`**:
```json
{
  "service": {
    "id": 1,
    "name": "Plex",
    "host_label": "HOLYGRAIL",
    "host": "192.168.10.129",
    "port": 32400,
    "check_type": "http"
  },
  "history": [
    {
      "checked_at": "2026-04-09T14:32:00Z",
      "status": "green",
      "response_time_ms": 45,
      "error": null
    },
    {
      "checked_at": "2026-04-09T14:31:00Z",
      "status": "yellow",
      "response_time_ms": 2150,
      "error": null
    }
  ]
}
```

**Response `404 Not Found`**: service ID does not exist or is disabled.

---

### `GET /containers`

Returns the current Docker container snapshot from HOLYGRAIL. Uses last known state if socket is unavailable.

**Response `200 OK`**:
```json
{
  "refreshed_at": "2026-04-09T14:32:00Z",
  "socket_error": false,
  "running": [
    {
      "id": "abc123def456",
      "name": "plex",
      "image": "linuxserver/plex:latest",
      "status": "running",
      "ports": {"32400/tcp": 32400},
      "uptime": "3 days, 2:14:08",
      "created": "2026-04-06T10:00:00Z"
    }
  ],
  "stopped": [
    {
      "id": "dead000beef0",
      "name": "old-container",
      "image": "some/image:tag",
      "status": "exited",
      "ports": {},
      "uptime": null,
      "created": "2026-04-01T08:00:00Z"
    }
  ]
}
```

When `socket_error: true`:
- `running` and `stopped` contain the last successfully fetched data (may be stale)
- `refreshed_at` reflects when the last successful fetch occurred
- Frontend MUST display a staleness warning banner when `socket_error` is `true`

When no data has been fetched yet (app just started):
- `running: []`, `stopped: []`, `refreshed_at: null`, `socket_error: true`

---

### `GET /dashboard/summary`

Returns the overall system health summary for the banner.

**Response `200 OK`**:
```json
{
  "total": 12,
  "healthy": 10,
  "degraded": 1,
  "down": 1,
  "unchecked": 0,
  "hosts": [
    {
      "label": "HOLYGRAIL",
      "total": 6,
      "healthy": 6,
      "degraded": 0,
      "down": 0
    },
    {
      "label": "Torrentbox",
      "total": 4,
      "healthy": 3,
      "degraded": 1,
      "down": 0
    },
    {
      "label": "NAS",
      "total": 1,
      "healthy": 0,
      "degraded": 0,
      "down": 1
    },
    {
      "label": "Pi-hole DNS",
      "total": 1,
      "healthy": 1,
      "degraded": 0,
      "down": 0
    }
  ]
}
```

`unchecked` = services with no check result yet (e.g., just seeded).

---

## Unchanged Existing Endpoints

| Endpoint | Status |
|----------|--------|
| `GET /health` | Unchanged |
| `GET /devices` | Unchanged |
| `GET /devices/{mac}` | Unchanged |
| `PATCH /devices/{mac}/annotation` | Unchanged |
| `GET /events` | Unchanged |
| `GET /scans` | Unchanged |
| `POST /scans/trigger` | Unchanged |
| `GET /ai-context` | Unchanged |

---

## Error Responses

All endpoints follow the existing FastAPI pattern:

```json
{ "detail": "Human-readable error message" }
```

Standard HTTP status codes: `400` bad request, `404` not found, `422` validation error, `500` internal server error.
