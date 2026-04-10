# Data Model: Service Registry & Health Dashboard

**Phase**: 1 — Design  
**Branch**: `009-service-registry-dashboard`  
**Date**: 2026-04-09

---

## Overview

Two new database tables are introduced. The existing `services` table (network discovery) is untouched. Container state is ephemeral (in-memory only, no DB table).

```
service_definitions  ────┐
                          │ 1:M
health_check_results  ◄───┘

(existing tables unchanged)
devices ◄── services (network discovery, untouched)
```

---

## New Tables

### `service_definitions`

Represents a configured, health-checked service endpoint. Seeded via Alembic migration; no runtime CRUD API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, autoincrement | Surrogate key |
| `name` | VARCHAR(100) | NOT NULL | Display name (e.g., "Plex", "Deluge") |
| `host_label` | VARCHAR(100) | NOT NULL | Human-readable host name (e.g., "HOLYGRAIL", "Torrentbox") |
| `host` | VARCHAR(255) | NOT NULL | IP or hostname (e.g., "192.168.10.129") |
| `port` | INTEGER | NOT NULL | TCP port to check |
| `check_type` | VARCHAR(10) | NOT NULL | `"http"` \| `"tcp"` |
| `check_url` | VARCHAR(255) | nullable | HTTP path for HTTP checks (e.g., `"/health"`). NULL for TCP checks. |
| `check_interval_seconds` | INTEGER | NOT NULL, default 60 | How often to probe |
| `degraded_threshold_ms` | INTEGER | nullable | HTTP only: response time (ms) above which status = yellow. Default 2000. NULL for TCP. |
| `enabled` | BOOLEAN | NOT NULL, default true | If false, skipped by health checker |
| `created_at` | TIMESTAMP | NOT NULL, server_default now() | Row creation time |

**Indexes**: `(host_label)` for grouping queries; `(enabled)` for health checker filter.

**Uniqueness**: `(name, host)` — prevents duplicate definitions for the same service on the same host.

---

### `health_check_results`

One row per health check probe execution. Retained for 7 days; older rows purged automatically by the background task.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, autoincrement | Surrogate key |
| `service_id` | INTEGER | FK → `service_definitions.id` ON DELETE CASCADE, NOT NULL | Parent service |
| `checked_at` | TIMESTAMP | NOT NULL, indexed DESC | When the probe ran |
| `status` | VARCHAR(10) | NOT NULL | `"green"` \| `"yellow"` \| `"red"` |
| `response_time_ms` | INTEGER | nullable | Round-trip time in ms. NULL if unreachable. |
| `error` | TEXT | nullable | Error message if status = red (timeout, connection refused, etc.) |

**Indexes**:
- `(service_id, checked_at DESC)` — primary query pattern (latest results per service, history for a service)
- `(checked_at)` — for time-based purge (`DELETE WHERE checked_at < now() - 7 days`)

**Retention**: Background task deletes rows where `checked_at < NOW() - INTERVAL '7 days'` on each cycle.

---

## In-Memory State (not persisted)

`app.state.container_state` — updated every 60 seconds by the background task.

```python
{
    "running": [
        {
            "id": "abc123",           # short container ID (first 12 chars)
            "name": "plex",           # container name (without leading /)
            "image": "linuxserver/plex:latest",
            "status": "running",       # Docker status string
            "ports": {"32400/tcp": 32400},  # exposed host port mapping
            "uptime": "3 days, 2:14:08",   # human-readable uptime
            "created": "2026-04-06T10:00:00Z"
        },
        ...
    ],
    "stopped": [
        { ... }   # same shape, status = "exited" or other non-running
    ],
    "refreshed_at": "2026-04-09T14:32:00Z",   # ISO8601 UTC
    "socket_error": false                        # true = last fetch failed, data is stale
}
```

---

## Entity Relationships (full picture)

```
devices (existing)
  └── services (existing — network discovery only, untouched)
  └── annotations (existing)
  └── events (existing)
  └── alerts (existing)

service_definitions (NEW)
  └── health_check_results (NEW, ON DELETE CASCADE)
```

---

## Migration: `002_service_registry.py`

**Up**:
1. Create `service_definitions` table with all columns + indexes
2. Create `health_check_results` table with all columns + indexes
3. Insert seed rows for 12 known services (see research.md Decision 4)

**Down**:
1. Drop `health_check_results`
2. Drop `service_definitions`

---

## Derived Views (API-level, not DB views)

**Latest health status per service** (used by `GET /services`):
```sql
SELECT DISTINCT ON (service_id)
    service_id, status, checked_at, response_time_ms, error
FROM health_check_results
ORDER BY service_id, checked_at DESC
```

**Dashboard summary** (used by `GET /dashboard/summary`):
```
total     = COUNT(*) FROM service_definitions WHERE enabled = true
healthy   = COUNT where latest status = 'green'
degraded  = COUNT where latest status = 'yellow'
down      = COUNT where latest status = 'red'
```
