# Implementation Plan: Network Advisor Application Scaffold

**Branch**: `007-advisor-app-scaffold` | **Date**: 2026-04-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-advisor-app-scaffold/spec.md`

## Summary

Scaffold the Network Advisor as a full-stack web application: FastAPI backend (Python 3.12+), React + TypeScript + Tailwind frontend (Vite), PostgreSQL database, all orchestrated by Docker Compose. The stack integrates with HOLYGRAIL's existing Traefik reverse proxy at `advisor.holygrail`. No business logic — just the skeleton for F4.2+ features to build on.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI, uvicorn, SQLAlchemy, asyncpg, psycopg2 (backend); React 18, Vite 5, Tailwind CSS 3 (frontend)
**Storage**: PostgreSQL 16 (Docker container, named volume)
**Testing**: pytest (backend), Vitest + React Testing Library (frontend) — scaffolded but not populated (test-after per constitution)
**Target Platform**: Linux x86_64 (HOLYGRAIL — Ryzen 7800X3D / 32GB / Ubuntu 24.04)
**Project Type**: Full-stack web service (Docker Compose orchestrated)
**Performance Goals**: Health endpoint <2s response, frontend load <3s, full stack startup <60s
**Constraints**: Local-network only, single user, no cloud dependencies, no auth
**Scale/Scope**: 5 network devices, single admin user, ~3 database tables

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Local-First | PASS | All services on LAN (192.168.10.0/24). No cloud APIs. Ollama URL accepted as env var only. |
| II. Simplicity & Pragmatism | PASS | Standard stack, no enterprise patterns. Raw SQL init script (no Alembic yet — YAGNI). Single Compose file. |
| III. Containerized Everything | PASS | All services in Docker Compose. Named volumes for data. `restart: unless-stopped`. Secrets in `.env` (gitignored). |
| IV. Test-After | PASS | Test directories scaffolded with config but no test files. Tests written after implementation. |
| V. Observability | PASS | `/health` endpoint with deep DB check. Structured JSON logs to stdout. Future Grafana dashboard deferred to F4.2+. |

**Gate result: PASS — no violations.**

## Project Structure

### Documentation (this feature)

```text
specs/007-advisor-app-scaffold/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.md           # REST API contract (health endpoint)
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
advisor/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI app factory, CORS, lifespan
│   │   ├── config.py         # Pydantic settings from env vars
│   │   ├── database.py       # SQLAlchemy async engine + session
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── health.py     # GET /health (deep check)
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── device.py     # Device ORM model
│   │       ├── service.py    # Service ORM model
│   │       └── alert.py      # Alert ORM model
│   ├── tests/                # Empty — test-after
│   ├── requirements.txt      # Pinned dependencies
│   └── Dockerfile            # Python 3.12-slim, uvicorn
├── frontend/
│   ├── src/
│   │   ├── components/       # Reusable UI components (empty)
│   │   ├── pages/            # Page-level components
│   │   │   └── Home.tsx      # Default landing page
│   │   ├── services/         # API client utilities (empty)
│   │   ├── App.tsx           # Root component + router shell
│   │   ├── main.tsx          # Entry point
│   │   └── index.css         # Tailwind directives
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts        # Dev proxy to backend
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   ├── nginx.conf            # Production: proxy /api → backend
│   ├── tests/                # Empty — test-after
│   └── Dockerfile            # Multi-stage: build → nginx
├── db/
│   └── init.sql              # Schema + seed data (5 devices)
├── docker-compose.yml        # Backend, frontend, postgres
└── .env.example              # Template for required env vars
```

**Structure Decision**: Web application layout with `backend/` + `frontend/` + `db/` under `advisor/` at repo root. Matches CLAUDE.md convention (`advisor/` — Network Advisor app). Single `docker-compose.yml` at `advisor/` level orchestrates all three services. Integrates with HOLYGRAIL's existing `holygrail-proxy` external network for Traefik routing.
