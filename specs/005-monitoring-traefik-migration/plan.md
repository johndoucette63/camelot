# Implementation Plan: Monitoring Migration & Traefik Reverse Proxy

**Branch**: `005-monitoring-traefik-migration` | **Date**: 2026-04-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-monitoring-traefik-migration/spec.md`

## Summary

Migrate the monitoring stack (Grafana, InfluxDB 1.8, Smokeping, exporter, speedtest) from Torrentbox (Pi 5) to HOLYGRAIL (Ryzen 7800X3D) and deploy Traefik as a reverse proxy for hostname-based access to all HOLYGRAIL services. This centralizes monitoring on the most capable machine, establishes the routing layer for future services (Ollama, Network Advisor), and builds the data pipeline that Phase 3+ AI features will consume.

## Technical Context

**Language/Version**: Bash (POSIX shell scripts), Docker Compose YAML, Python 3.11+ (existing monitoring scripts)  
**Primary Dependencies**: Docker Compose v2, Traefik (latest), Grafana (latest), InfluxDB 1.8, Smokeping (linuxserver), Python 3.11  
**Storage**: InfluxDB 1.8 (time-series in Docker volume), Grafana (Docker volume), Smokeping RRD (Docker volume)  
**Testing**: Manual verification + shell-based validation scripts (test-after per Constitution IV)  
**Target Platform**: HOLYGRAIL (Ubuntu 24.04 LTS, x86_64) + Mac workstation (DNS config)  
**Project Type**: Infrastructure/DevOps (Docker Compose deployment)  
**Performance Goals**: N/A — monitoring services, not high-throughput application  
**Constraints**: LAN-only (Constitution I), auto-restart on reboot, no cloud dependencies  
**Scale/Scope**: Single admin, 6 service containers (monitoring) + 1 container (Traefik), 1 server

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --- | --- | --- |
| I. Local-First | PASS | All services on LAN (192.168.10.0/24). No cloud APIs, SaaS, or external accounts. InfluxDB, Grafana, Smokeping all self-hosted. |
| II. Simplicity & Pragmatism | PASS | Docker Compose + shell scripts. No service mesh, no orchestrator. `/etc/hosts` for DNS (simplest approach). Standard Docker images. |
| III. Containerized Everything | PASS | All services containerized. Separate compose file per stack (monitoring, traefik, plex, portainer). Shared external network for Traefik routing. `restart: unless-stopped` on all. Secrets via `.env` files. |
| IV. Test-After | PASS | Verification scripts run after deployment, not before. No TDD. |
| V. Observability | PASS | This IS the observability infrastructure. All services have Docker healthchecks. Grafana dashboards provisioned automatically. Monitoring pipeline established before AI features (Phase 3+). Batch processes (exporter, speedtest) use Docker healthchecks as /health equivalent since they have no HTTP server. |

**Post-Phase 1 Re-check**: All gates still pass. Separate compose files per stack honor Constitution III. File-provider route for Plex (host-network) is the pragmatic solution per Constitution II.

## Project Structure

### Documentation (this feature)

```text
specs/005-monitoring-traefik-migration/
├── plan.md              # This file
├── research.md          # Phase 0 output — 8 research decisions
├── data-model.md        # Phase 1 output — InfluxDB measurements, Traefik routes, Docker networks
├── quickstart.md        # Phase 1 output — deployment steps and verification
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
infrastructure/holygrail/
├── monitoring/
│   ├── docker-compose.yml       # NEW — Grafana, InfluxDB, Smokeping, exporter, speedtest
│   └── .env.example             # NEW — credential template (GRAFANA_ADMIN_PASSWORD, INFLUXDB_*)
├── traefik/
│   ├── docker-compose.yml       # NEW — Traefik reverse proxy
│   ├── config/
│   │   └── dynamic.yml          # NEW — file-provider routes (Plex host-network)
│   └── .env.example             # NEW — Traefik config template
├── plex/
│   └── docker-compose.yml       # EXISTING — no changes (host network, routed via file provider)
└── docker/
    └── portainer-compose.yml    # MODIFIED — add holygrail-proxy network + Traefik labels

infrastructure/monitoring/
├── smokeping/
│   └── Targets                  # MODIFIED — update Plex→HOLYGRAIL target
├── grafana/
│   ├── dashboards/
│   │   └── network-monitoring.json  # EXISTING — no changes (uses datasource variable)
│   └── provisioning/
│       ├── datasources/
│       │   └── influxdb.yml     # MODIFIED — URL from host.docker.internal to influxdb:8086
│       └── dashboards/
│           └── default.yml      # EXISTING — no changes
└── scripts/
    ├── smokeping_exporter.py    # EXISTING — no changes (env vars drive connection)
    ├── speedtest_logger.py      # EXISTING — no changes
    ├── requirements-exporter.txt    # EXISTING — no changes
    └── requirements-speedtest.txt   # EXISTING — no changes

docs/
└── INFRASTRUCTURE.md            # MODIFIED — update service locations table

scripts/
└── setup-holygrail-dns.sh      # NEW — Mac /etc/hosts setup helper (optional)
```

**Structure Decision**: Separate compose files per service stack per Constitution III. Shared `holygrail-proxy` external Docker network enables Traefik routing across stacks. Monitoring configs remain in `infrastructure/monitoring/` (shared between source and deployment), copied to HOLYGRAIL during deployment.

## Complexity Tracking

> No constitution violations. No justifications needed.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --- | --- | --- |
| (none) | — | — |
