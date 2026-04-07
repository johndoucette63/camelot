<!--
  Sync Impact Report
  ==================
  Version change: 0.0.0 (template) → 1.0.0
  Modified principles: N/A (initial ratification)
  Added sections:
    - I. Local-First
    - II. Simplicity & Pragmatism
    - III. Containerized Everything
    - IV. Test-After (Not Test-First)
    - V. Observability
    - Technology Stack
    - Development Workflow
    - Governance
  Removed sections: All template placeholders replaced
  Templates requiring updates:
    - .specify/templates/plan-template.md — ⚠ pending (Constitution Check
      section is generic; will be filled per-feature by /speckit.plan)
    - .specify/templates/spec-template.md — ✅ no changes needed
    - .specify/templates/tasks-template.md — ⚠ note: template references
      "Write tests FIRST" and TDD language in several places. This conflicts
      with Principle IV (Test-After). The template is advisory and task
      generation via /speckit.tasks MUST reorder tests to come AFTER
      implementation, not before.
  Follow-up TODOs: None
-->

# Camelot Constitution

## Core Principles

### I. Local-First

All services and data MUST remain on the local network (192.168.10.0/24).
No cloud APIs, SaaS dependencies, or external accounts are required for
core functionality. Data never leaves the LAN unless the owner explicitly
chooses otherwise (e.g., VPN, Tailscale).

- Privacy is non-negotiable — no telemetry, no cloud sync, no external auth.
- The system MUST be fully operational with no internet connectivity
  (except for initial package/image pulls and torrent traffic).
- Ollama provides LLM inference locally; never call OpenAI/Anthropic APIs
  from production services.

### II. Simplicity & Pragmatism

This is a single-owner project. Every decision MUST be evaluated against
the question: "Is this the simplest thing that works?"

- YAGNI applies everywhere. Do not build for hypothetical future needs.
- Scripts MUST be small, focused, and readable. Prefer one script per task
  over a monolithic utility.
- Prefer the obvious solution over the clever one.
- No enterprise patterns: no service mesh, no event bus, no saga
  orchestrators, no abstract factory factories.
- If a shell script solves the problem, do not write a Python package.

### III. Containerized Everything

All long-running services MUST run as Docker containers orchestrated by
Docker Compose. Configuration lives in the repo; data lives in volumes.

- ARM64 images for Raspberry Pi services, x86_64 for HOLYGRAIL.
- Each service stack gets its own `docker-compose.yml` in the appropriate
  `infrastructure/` subdirectory.
- Containers MUST restart on failure (`restart: unless-stopped` minimum).
- No Kubernetes, no Swarm, no Nomad. Compose is the ceiling.
- Secrets MUST NOT be committed to the repo. Use `.env` files (gitignored)
  or Docker secrets.

### IV. Test-After (Not Test-First)

Implementation comes first. Tests come after, validating the implemented
behavior. TDD is explicitly **not** used in this project.

- Tests are REQUIRED for:
  - **Python backends**: pytest (API endpoint tests, service logic tests).
  - **React frontends**: Vitest + React Testing Library (component and
    integration tests).
- Tests MUST validate behavior and user-facing outcomes, not internal
  implementation details.
- Do not mock aggressively — prefer integration-style tests that exercise
  real code paths. Mock only external boundaries (network, hardware).
- Test files live alongside source in a `tests/` directory at the same
  level as `src/`.

### V. Observability

If it runs, it MUST be observable. Silent failures are unacceptable.

- All services MUST expose a `/health` endpoint (HTTP 200 when healthy).
- Logs MUST be structured (JSON preferred) and written to stdout/stderr
  for Docker log collection.
- Monitoring via Grafana + InfluxDB is a first-class concern, not an
  afterthought. New services SHOULD ship with a basic Grafana dashboard
  or InfluxDB write points.
- Alerts for critical failures (service down, disk full, device offline)
  MUST be surfaced in the Network Advisor dashboard.

## Technology Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Scripts & utilities | Python 3.12+ | Small, focused programs |
| Backend services | FastAPI (Python) | Async, OpenAPI docs auto-generated |
| Frontend | React + TypeScript + Tailwind CSS | Vite for build tooling |
| Database | PostgreSQL | Only where persistence is needed |
| LLM inference | Ollama | GPU-accelerated via NVIDIA runtime |
| Infrastructure | Docker Compose | One Compose file per service stack |
| Monitoring | Grafana + InfluxDB + Smokeping | Time-series metrics and latency |
| Reverse proxy | Traefik | Clean LAN URLs for all services |

**Prohibited technologies** (to prevent scope creep):
- Kubernetes, Docker Swarm, or any container orchestrator beyond Compose.
- Cloud-hosted databases, queues, or storage (RDS, SQS, S3, etc.).
- CI/CD platforms (GitHub Actions, Jenkins, etc.) — all deployment is local.
- GraphQL — REST is sufficient for this project's complexity.

## Development Workflow

- **Branching**: spec-kit managed. `specify --number F1.1 ...` creates
  feature branches with spec-aligned numbering.
- **Testing**: Implement first, test after. Tests are required but not
  written before the code they validate.
- **Deployment**: `docker compose up -d` on the target machine. No
  pipelines, no staging environments, no blue-green deploys.
- **Single developer**: No pull request reviews, no approval gates, no
  CODEOWNERS. Commit directly to feature branches, merge to master when
  ready.
- **Commit discipline**: Small, focused commits. Each commit SHOULD leave
  the system in a working state.

## Governance

This constitution is the authoritative source for project-wide decisions.
It supersedes ad-hoc choices made in individual specs or plans.

- **Amendments** require updating this file, incrementing the version, and
  documenting the change in the Sync Impact Report comment block above.
- **Versioning** follows semver:
  - MAJOR: Principle removed, redefined, or made backward-incompatible.
  - MINOR: New principle or section added, or existing one materially
    expanded.
  - PATCH: Wording clarifications, typo fixes, non-semantic changes.
- **Compliance**: The Constitution Check section in each plan.md MUST
  verify that the planned work does not violate these principles. If a
  violation is necessary, it MUST be justified in the Complexity Tracking
  table.

**Version**: 1.0.0 | **Ratified**: 2026-04-06 | **Last Amended**: 2026-04-06
