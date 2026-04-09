# API Contract: Network Advisor Backend

**Feature**: 007-advisor-app-scaffold
**Date**: 2026-04-08
**Base URL**: `http://advisor.holygrail/api`

## Endpoints

### GET /health

Deep health check that verifies the backend and its database connection.

**Request**: No parameters.

**Response (healthy)**: HTTP 200

```json
{
  "status": "ok",
  "database": "connected"
}
```

**Response (unhealthy)**: HTTP 503

```json
{
  "status": "degraded",
  "database": "disconnected"
}
```

**Behavior**:
- Returns 200 only when the backend process is running AND the database connection succeeds.
- Returns 503 if the database is unreachable (backend is alive but not ready).
- Response time target: <2 seconds.

## Routing

All API endpoints are served under the `/api` prefix. The frontend's nginx (production) and Vite dev server (development) proxy `/api/*` requests to the backend on port 8000.

| Path | Backend Route | Description |
| ---- | ------------- | ----------- |
| `/api/health` | `GET /health` | Deep health check |

Future F4.2+ endpoints (devices, services, alerts, chat) will follow the same `/api/` prefix convention.

## Error Format

All error responses use a consistent JSON structure:

```json
{
  "detail": "Human-readable error message"
}
```

This is FastAPI's default error format and will be used for all 4xx/5xx responses.
