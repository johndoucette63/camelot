# Research: Network Advisor Application Scaffold

**Feature**: 007-advisor-app-scaffold
**Date**: 2026-04-08

## R1: Database Migration Strategy

**Decision**: Raw SQL init script (`db/init.sql`) executed by PostgreSQL's `/docker-entrypoint-initdb.d/` mechanism.

**Rationale**: The constitution mandates simplicity (Principle II — YAGNI). This scaffold has exactly one schema version with no migration history. PostgreSQL's built-in init script support requires zero additional dependencies. Alembic adds complexity (migration files, env.py, alembic.ini) that is unnecessary until schema evolution actually happens in F4.2+.

**Alternatives considered**:
- **Alembic**: Full migration framework. Rejected — premature for a scaffold with a single schema version. Can be introduced in F4.2 when the schema actually needs to evolve.
- **SQLAlchemy `create_all()`**: Auto-generate tables from ORM models at startup. Rejected — doesn't support seed data insertion cleanly, and mixes schema management with application startup.

## R2: Frontend Production Serving

**Decision**: Multi-stage Dockerfile — Stage 1: `node:20-alpine` builds the Vite app. Stage 2: `nginx:alpine` serves the static build output and proxies `/api/` requests to the backend.

**Rationale**: nginx is the standard production server for SPAs. Multi-stage builds keep the final image small (no Node.js runtime in production). The nginx config handles both static file serving and API proxying, eliminating CORS issues without additional backend configuration.

**Alternatives considered**:
- **Serve via Node.js** (e.g., `serve` package): Rejected — adds Node.js runtime to production image unnecessarily. nginx is lighter and more battle-tested for static files.
- **Backend serves frontend**: Rejected — couples frontend deployment to backend, making independent iteration harder.

## R3: Frontend Development Proxy

**Decision**: Vite dev server's built-in proxy (`vite.config.ts` → `server.proxy`) routes `/api/` requests to the backend container during local development.

**Rationale**: Vite's proxy is zero-config beyond a few lines in `vite.config.ts`. It provides the same URL structure in dev and production, so frontend code doesn't need environment-specific API base URLs.

**Alternatives considered**:
- **CORS headers on backend**: Rejected — adds backend complexity and diverges dev/prod behavior.
- **Separate API base URL env var**: Rejected — unnecessary indirection when proxy handles it transparently.

## R4: Traefik Integration Pattern

**Decision**: The advisor's `docker-compose.yml` joins the existing `holygrail-proxy` external network. The frontend (nginx) container gets Traefik labels routing `advisor.holygrail` to its port. The backend is not exposed directly via Traefik — it's proxied through nginx's `/api/` route.

**Rationale**: This matches the pattern used by all other HOLYGRAIL services (Grafana, Ollama, Smokeping). Only one Traefik-routed entry point per stack keeps routing simple. The frontend's nginx handles the backend proxy internally, so Traefik only sees one service.

**Alternatives considered**:
- **Traefik routes both frontend and backend separately** (e.g., `advisor.holygrail` for frontend, `advisor-api.holygrail` for backend): Rejected — over-engineering for a single-user app. Two hostnames adds DNS/Pi-hole complexity for no benefit.
- **Traefik path-based routing** (`/api` → backend, `/` → frontend): Possible but adds Traefik middleware complexity. Simpler to let nginx handle it within the stack.

## R5: Backend Async Database Driver

**Decision**: SQLAlchemy 2.0 async with `asyncpg` driver for async operations, `psycopg2-binary` for health checks and sync utilities.

**Rationale**: FastAPI is async-native. SQLAlchemy 2.0's async support is mature and works well with `asyncpg` for high-performance async queries. `psycopg2-binary` provides a sync fallback for simple operations (health check DB ping) without requiring an async session.

**Alternatives considered**:
- **Sync-only SQLAlchemy**: Rejected — blocks the FastAPI event loop, negating async benefits.
- **Raw asyncpg without SQLAlchemy**: Rejected — loses ORM benefits (model definitions, query building) that will be valuable in F4.2+ feature development.

## R6: Backend Structured Logging

**Decision**: Python's `logging` module configured to output JSON-formatted logs to stdout via `python-json-logger`.

**Rationale**: Constitution Principle V requires structured (JSON preferred) logs to stdout for Docker log collection. `python-json-logger` is a lightweight single-purpose library that formats standard Python log records as JSON. No complex logging framework needed.

**Alternatives considered**:
- **structlog**: More powerful but heavier. Rejected — YAGNI for a scaffold.
- **Plain text logging**: Rejected — constitution explicitly prefers JSON structured logs.
