# Research: Service Registry & Health Dashboard

**Phase**: 0 — Research  
**Branch**: `009-service-registry-dashboard`  
**Date**: 2026-04-09

---

## Decision 1: Docker Socket Access Pattern

**Decision**: Use `docker` SDK (docker-py) with `asyncio.to_thread()` for all blocking calls.

**Rationale**: docker-py is synchronous. For ~15 containers polled every 60 seconds, wrapping blocking calls in `asyncio.to_thread()` is the simplest approach that keeps the event loop unblocked. The overhead of spawning one thread per 60-second cycle is negligible. `aiodocker` (native async) would also work but adds a new dependency with no meaningful benefit at this scale.

**Alternatives considered**:
- `aiodocker` — pure async, no thread overhead. Rejected: extra dependency, meaningfully more complex API, no benefit for this polling frequency.
- Per-request `docker.from_env()` — creates new connections each call. Rejected: wasteful; singleton with connection pooling is correct.

**Implementation**: Singleton `docker.DockerClient` created once in the FastAPI `lifespan` context, stored on `app.state.docker`. Socket unavailability caught via `docker.errors.DockerException`.

---

## Decision 2: Health Check Background Task Architecture

**Decision**: Single `asyncio.create_task()` started in the FastAPI `lifespan` context (not a separate Docker container).

**Rationale**: The scanner runs as a separate container because it needs `network_mode: host` for ARP/MAC discovery. The health checker has no such requirement — it only needs TCP/HTTP access to LAN IPs (192.168.10.0/24), which is reachable from the advisor's bridge network through the host's routing table, and Docker socket access (a volume mount). Running the health checker inside the FastAPI process avoids a new container, new entrypoint file, and new Compose service.

**Pattern**:
```
lifespan startup → asyncio.create_task(run_health_checker(app))
  ↓ every 60s:
  1. Refresh Docker containers via docker socket → app.state.container_state
  2. Run all enabled ServiceDefinition checks (HTTP / TCP)
  3. Write HealthCheckResult rows to DB
  4. Purge HealthCheckResult rows older than 7 days
lifespan shutdown → task.cancel() + await task
```

SQLAlchemy sessions: background task uses `async with async_session() as session` directly (not the request-scoped `Depends(get_db)` dependency).

**Alternatives considered**:
- Separate `health_checker` Docker container (like scanner) — rejected: no `network_mode: host` requirement, adds unnecessary Compose complexity.
- APScheduler — rejected: already absent from the codebase; asyncio task is simpler and sufficient.
- Celery — rejected: overkill for a single recurring task; Constitution principle II (no enterprise patterns).

---

## Decision 3: Container State Storage (In-Memory vs DB)

**Decision**: Container snapshots stored in-memory on `app.state.container_state`. No DB table for container history.

**Rationale**: The spec requires showing the _current_ container state (refreshed every 60s), with "last known state + staleness warning" when the socket is unavailable. This is a single-snapshot concern, not a time-series concern. Storing in `app.state` is sufficient, zero-schema-cost, and aligns with YAGNI. Health check results (which _are_ time-series) go to DB.

`app.state.container_state` shape:
```python
{
    "containers": [...],       # list of container dicts (running)
    "stopped": [...],          # list of container dicts (stopped/exited)
    "refreshed_at": datetime,  # when this was last successfully fetched
    "socket_error": bool       # True if last fetch failed
}
```

**Alternatives considered**:
- DB table `container_snapshots` — rejected: no history requirement in spec; adds schema without value.
- Redis — rejected: not in the project stack; out of scope.

---

## Decision 4: Service Definition Management

**Decision**: Service definitions are seeded via Alembic migration 002. No CRUD UI or admin API.

**Rationale**: Resolved in clarification session (Q1: config/seed only). Alembic migration is the existing pattern for seeded data (see migration 001 which seeds 5 known devices). New services can be added by writing a new migration.

**Seed services** (from spec FR-013 + known Camelot infrastructure):

| Name | Host | Port | Check Type | Check URL / Note |
|------|------|------|------------|------------------|
| Plex | 192.168.10.129 | 32400 | HTTP | `/identity` |
| Ollama | 192.168.10.129 | 11434 | HTTP | `/api/tags` |
| Grafana | 192.168.10.129 | 3000 | HTTP | `/api/health` |
| Portainer | 192.168.10.129 | 9000 | HTTP | `/api/status` |
| Traefik | 192.168.10.129 | 8080 | TCP | — |
| Advisor | 192.168.10.129 | 8000 | HTTP | `/health` |
| Deluge | 192.168.10.141 | 8112 | HTTP | `/` (login page = 200) |
| Sonarr | 192.168.10.141 | 8989 | HTTP | `/api/v3/health` |
| Radarr | 192.168.10.141 | 7878 | HTTP | `/api/v3/health` |
| Prowlarr | 192.168.10.141 | 9696 | HTTP | `/` |
| SMB (NAS) | 192.168.10.105 | 445 | TCP | — |
| Pi-hole | 192.168.10.150 | 80 | HTTP | `/admin/` |

---

## Decision 5: Existing `Service` Model Relationship

**Decision**: Leave the existing `services` table untouched. Introduce `service_definitions` and `health_check_results` as new tables.

**Rationale**: The existing `Service` model is a network-discovery artifact — it represents services *detected* on a device (by nmap or annotation). It has no health check semantics. The new `ServiceDefinition` is a *configured* health check target — a different concept with different attributes (check_type, check_url, degraded_threshold_ms, etc.). Conflating them would require nullable columns and awkward conditionals. Clean separation follows the data model in the spec.

**Alternatives considered**:
- Extend existing `services` table with health check columns — rejected: conflates two different concerns (discovered port vs. configured health check); requires nullability for most new fields on existing rows.

---

## Decision 6: Yellow/Degraded Status Scope

**Decision**: Yellow status applies to HTTP checks only (response time > 2000ms). TCP checks are binary (green/red).

**Rationale**: Resolved in clarification session (Q5). TCP connection establishment has no meaningful intermediate state at LAN speeds. A slow TCP handshake on a home LAN indicates something unusual; treat it as red (unreachable) rather than creating a confusing yellow state.

**Implementation**: `HealthChecker.check_http()` compares `response_time_ms` against `degraded_threshold_ms` (default 2000). `HealthChecker.check_tcp()` returns `"green"` or `"red"` only, ignoring `degraded_threshold_ms`.
