# Camelot

Unified home infrastructure platform. Raspberry Pis handle dedicated edge workloads (torrents, NAS, IoT), HOLYGRAIL is the central server (media, AI, monitoring), and the Mac is the development/management workstation. Everything is managed from this repo.

## Architecture

5-device network on `192.168.10.0/24`:

| Device | IP | Role | SSH |
|--------|-----|------|-----|
| HOLYGRAIL | 192.168.10.129 | Ryzen 7800X3D / 32GB / RTX 2070S — central server | `ssh john@holygrail` |
| Torrentbox | 192.168.10.141 | Pi 5 — Deluge + *arr apps + VPN | `ssh john@192.168.10.141` |
| NAS | 192.168.10.105 | Pi 4 — OpenMediaVault, SMB shares | `ssh pi@192.168.10.105` |
| Pi-hole DNS | 192.168.10.150 | Pi 5 — Pi-hole DNS (Plex + Emby migrated to HOLYGRAIL) | `ssh pi@192.168.10.150` |
| Mac Workstation | 192.168.10.145 | MacBook Pro M4 Pro — dev/management only | N/A |

The Mac is **not a service host**. HOLYGRAIL is the heavy-lifting server. Pis handle dedicated edge tasks.

## Key Files

- `docs/` — Specs, plans, and guides (spec-kit compatible)
  - `PROJECT-PLAN.md` — Master plan with all phases and dependencies
  - `INFRASTRUCTURE.md` — Full network topology, hardware specs, Docker configs, credentials
  - `network-advisor-spec.md` — AI-powered network advisor application spec
- `infrastructure/` — Device-specific configs
  - `torrentbox/` — Pi torrent stack (future: Docker Compose from Pi)
  - `holygrail/` — HOLYGRAIL Docker Compose (Plex, Ollama, Traefik, monitoring)
  - `monitoring/` — Monitoring stack (Smokeping, Grafana, InfluxDB — migrating to HOLYGRAIL)
- `advisor/` — Network Advisor app (FastAPI + React + PostgreSQL — Phase 4)
- `scripts/` — Mac-side management tools
  - `ssh-config` — SSH config for all devices (include in ~/.ssh/config)
  - `pi-status.sh` — Remote status checker (uptime, disk, Docker, temps, updates)
  - `pi-update.sh` — Remote OS + Docker updater with interactive confirmations
  - `deluge-monitor.py` — Torrent health monitor (exe detection, stalled, cleanup)
  - `benchmark-drives.sh` — Cross-platform disk benchmark (Linux + macOS)

## Development Notes

- Mac is management only — never runs services
- HOLYGRAIL runs heavy workloads: Plex (NVENC), Ollama (CUDA), monitoring, advisor
- Pis stay dedicated: Torrentbox (downloads), NAS (storage), Home Assistant (IoT)
- Docker Compose: ARM64 for Pis, x86_64 for HOLYGRAIL
- Scripts should be cross-platform where possible (Linux + macOS)
- Torrent flow: Prowlarr -> Deluge (VPN) -> Sonarr/Radarr (rename) -> NAS -> Plex
- HOLYGRAIL runs Ubuntu 24.04 LTS (Phase 1 complete)

## Project Phases

See `docs/PROJECT-PLAN.md` for the full plan. Summary:

| Phase | Status | Description |
|-------|--------|-------------|
| 0 — Foundation | Done | Docs, scripts, repo structure |
| 1 — HOLYGRAIL Setup | Done | Ubuntu install, Docker, NVIDIA, Portainer |
| 2 — Service Migration | In Progress | Plex migrated; monitoring to HOLYGRAIL |
| 3 — Ollama & AI | Blocked on 1 | Local LLM with GPU acceleration |
| 4 — Network Advisor | Blocked on 1,3 | FastAPI + React advisor app |
| 5 — Torrent Expansion | Independent | Paid indexers, quality profiles |
| 6 — Home Assistant | Blocked on 4 | IoT/Thread integration |
| 7 — NAS Evolution | Blocked on 2 | Storage upgrade path |
| 8 — Network Monitoring | Blocked on 2,4 | Full inventory, logging, VLANs |

## Common Tasks

```bash
# SSH into devices (using ssh-config aliases)
ssh torrentbox   # or: ssh john@192.168.10.141
ssh nas          # or: ssh pi@192.168.10.105
ssh mediaserver  # or: ssh pi@192.168.10.150 (Pi-hole DNS)

# Check status of all Pis
bash scripts/pi-status.sh              # All devices
bash scripts/pi-status.sh torrentbox   # Single device

# Update OS and Docker on Pis
bash scripts/pi-update.sh all              # Everything
bash scripts/pi-update.sh torrentbox --docker  # Docker only on Torrentbox
bash scripts/pi-update.sh nas --os         # OS only on NAS

# Monitor Deluge torrents
python3 scripts/deluge-monitor.py              # Full health report
python3 scripts/deluge-monitor.py --check-exe  # Scan for exe files
python3 scripts/deluge-monitor.py --remove-exe # Remove bad torrents
python3 scripts/deluge-monitor.py --stalled    # Show stalled downloads
python3 scripts/deluge-monitor.py --cleanup    # Interactive cleanup

# Check VPN status
ssh torrentbox "docker exec deluge curl -s ifconfig.me"

# Run benchmarks
bash scripts/benchmark-drives.sh
```

## Active Technologies
- Bash (POSIX-compatible shell scripts) + Ubuntu Server 24.04 LTS, OpenSSH, UFW, Netplan 1.0 (001-ubuntu-migration)
- N/A (OS-level disk, no application storage) (001-ubuntu-migration)
- Bash (POSIX-compatible shell scripts) + NVIDIA driver (560-server), Docker Engine, Docker Compose v2, nvidia-container-toolkit, Portainer CE (002-docker-gpu-infra)
- Docker volumes for Portainer data; no application databases (002-docker-gpu-infra)
- Bash (POSIX-compatible shell scripts), Markdown documentation + Existing pi-status.sh/pi-update.sh scripts, OpenSSH, nvidia-smi, Docker CLI (003-network-integration)
- Bash (POSIX-compatible shell scripts) + Docker Compose v2, linuxserver/plex image, nvidia-container-toolkit, cifs-utils (004-plex-migration)
- NAS SMB shares (media), local Docker volume (Plex config/database), local path (transcode cache) (004-plex-migration)
- Bash (POSIX shell scripts), Docker Compose YAML, Python 3.11+ (existing monitoring scripts) + Docker Compose v2, Traefik (latest), Grafana (latest), InfluxDB 1.8, Smokeping (linuxserver), Python 3.11 (005-monitoring-traefik-migration)
- InfluxDB 1.8 (time-series in Docker volume), Grafana (Docker volume), Smokeping RRD (Docker volume) (005-monitoring-traefik-migration)
- Bash (POSIX shell scripts), Docker Compose YAML + Docker Compose v2, Ollama (latest), nvidia-container-toolkit, Traefik (existing) (006-ollama-gpu-deployment)
- Docker volume for model persistence (ollama_data) (006-ollama-gpu-deployment)
- Python 3.12+ (backend), TypeScript 5.x (frontend) + FastAPI, uvicorn, SQLAlchemy, asyncpg, psycopg2 (backend); React 18, Vite 5, Tailwind CSS 3 (frontend) (007-advisor-app-scaffold)
- PostgreSQL 16 (Docker container, named volume) (007-advisor-app-scaffold)
- Python 3.12 (backend + scanner), TypeScript 5.x (frontend) + FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.x, python-nmap 0.7.x, mac-vendor-lookup 0.3.x, APScheduler not used (simple asyncio loop); React 18, Tailwind CSS 3, Vite 5, TanStack Table v8 (sortable list) (008-network-discovery-inventory)
- PostgreSQL 16 (existing Docker volume, extended via Alembic migration) (008-network-discovery-inventory)
- Python 3.12 (backend), TypeScript 5.x (frontend) + FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg, `docker` SDK (docker-py), React 18, Tailwind CSS 3, TanStack React Table v8 (009-service-registry-dashboard)
- PostgreSQL 16 (existing `advisor_pgdata` volume, extended via Alembic migration 002) (009-service-registry-dashboard)
- Python 3.12 (backend), TypeScript 5.7 (frontend) + FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14, `httpx` 0.28 (already in `requirements.txt`, used as the Ollama client), Pydantic v2; React 18, Vite 6, Tailwind 3, react-router-dom 7, TanStack React Table 8 (not needed for this feature but available) (010-ai-advisor-chat)
- PostgreSQL 16 in the existing `advisor_pgdata` Docker volume, extended via Alembic migration `003_chat_conversations.py` adding `conversations` and `messages` tables (010-ai-advisor-chat)
- Python 3.12 (backend), TypeScript 5.7 (frontend) + FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14, `httpx` 0.28 (for Ollama + Home Assistant webhook calls, already in `requirements.txt`), Pydantic v2; React 18, Vite 6, Tailwind 3, react-router-dom 7, TanStack React Table 8 (used for the alert history table) (011-recommendations-alerts)
- PostgreSQL 16 in the existing `advisor_pgdata` Docker volume. Extended via a new Alembic migration `004_recommendations_alerts.py` which (a) adds lifecycle + rule columns to the existing `alerts` table, (b) creates `alert_thresholds`, `rule_mutes`, and `notification_sinks` tables (011-recommendations-alerts)
- Python 3.12 (backend), TypeScript 5.7 (frontend) + FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14, httpx 0.28; React 18, Vite 6, Tailwind CSS 3, react-router-dom 7, TanStack React Table 8, react-markdown 10 (012-advisor-learnings-notes)
- PostgreSQL 16 in existing `advisor_pgdata` Docker volume, extended via Alembic migration `005_advisor_notes.py` (012-advisor-learnings-notes)

## Recent Changes
- 006-ollama-gpu-deployment: Deployed Ollama LLM with GPU acceleration on HOLYGRAIL, Llama 3.1 8B default model, ollama.holygrail hostname routing
- 005-monitoring-traefik-migration: Migrated Grafana/InfluxDB/Smokeping from Torrentbox to HOLYGRAIL, deployed Traefik reverse proxy with *.holygrail hostname routing
- 001-ubuntu-migration: Added Bash (POSIX-compatible shell scripts) + Ubuntu Server 24.04 LTS, OpenSSH, UFW, Netplan 1.0
