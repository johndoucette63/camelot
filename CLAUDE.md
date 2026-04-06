# Camelot

Unified home infrastructure platform. Raspberry Pis handle dedicated edge workloads (torrents, NAS, IoT), HOLYGRAIL is the central server (media, AI, monitoring), and the Mac is the development/management workstation. Everything is managed from this repo.

## Architecture

5-device network on `192.168.10.0/24`:

| Device | IP | Role | SSH |
|--------|-----|------|-----|
| HOLYGRAIL | 192.168.10.TBD | Ryzen 7800X3D / 32GB / RTX 2070S — central server | `ssh john@holygrail` |
| Torrentbox | 192.168.10.141 | Pi 5 — Deluge + *arr apps + VPN | `ssh john@192.168.10.141` |
| NAS | 192.168.10.105 | Pi 4 — OpenMediaVault, SMB shares, Pi-hole | `ssh pi@192.168.10.105` |
| Media Server | 192.168.10.150 | Pi 5 — Plex + Emby (migrating to HOLYGRAIL) | `ssh pi@192.168.10.150` |
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
- HOLYGRAIL is still on Windows 11 — Ubuntu migration is Phase 1 (see PROJECT-PLAN.md)

## Project Phases

See `docs/PROJECT-PLAN.md` for the full plan. Summary:

| Phase | Status | Description |
|-------|--------|-------------|
| 0 — Foundation | Done | Docs, scripts, repo structure |
| 1 — HOLYGRAIL Setup | Next | Ubuntu install, Docker, NVIDIA, Portainer |
| 2 — Service Migration | Blocked on 1 | Plex + monitoring to HOLYGRAIL |
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
ssh mediaserver  # or: ssh pi@192.168.10.150

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
