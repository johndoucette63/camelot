# Implementation Plan: Plex Media Server Migration

**Branch**: `004-plex-migration` | **Date**: 2026-04-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-plex-migration/spec.md`

## Summary

Migrate Plex Media Server from Media Server Pi (192.168.10.150, "Herring") to HOLYGRAIL (192.168.10.129) with NVIDIA NVENC hardware transcoding via RTX 2070 Super. Deploy using Docker Compose with the linuxserver/plex image, host networking, and nvidia runtime. Mount NAS SMB shares via fstab with systemd automount. Run parallel with the Pi instance during validation, then cut over. Retire Emby. Reconfigure Sonarr/Radarr to notify the new Plex instance. Re-invite shared external users.

## Technical Context

**Language/Version**: Bash (POSIX-compatible shell scripts)  
**Primary Dependencies**: Docker Compose v2, linuxserver/plex image, nvidia-container-toolkit, cifs-utils  
**Storage**: NAS SMB shares (media), local Docker volume (Plex config/database), local path (transcode cache)  
**Testing**: Verification shell script (test-after pattern, consistent with verify-docker-gpu.sh from F1.2)  
**Target Platform**: Ubuntu Server 24.04 LTS (HOLYGRAIL, x86_64)  
**Project Type**: Infrastructure migration (Docker Compose + system configuration)  
**Performance Goals**: Hardware transcoding via NVENC, playback start within 5 seconds  
**Constraints**: Plex config must be on local storage (not SMB — SQLite corruption risk); consumer GPU limited to 3 concurrent NVENC sessions by default  
**Scale/Scope**: Household usage, 3-5 concurrent streams

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Local-First | PASS | Plex runs locally on HOLYGRAIL. Plex account is required for server claim and remote access but is an existing third-party service, not a new cloud dependency. Core LAN playback works after initial claim. No telemetry or cloud sync added. |
| II. Simplicity & Pragmatism | PASS | Docker Compose + shell scripts + fstab mounts. No enterprise patterns. One script per task. |
| III. Containerized Everything | PASS | Plex runs as Docker container via Compose. restart: unless-stopped. Secrets in .env (gitignored). Compose file in infrastructure/holygrail/plex/. |
| IV. Test-After | PASS | Implementation first. Verification script validates after deployment (matches F1.2 verify-docker-gpu.sh pattern). No TDD. |
| V. Observability | PASS | Docker healthcheck in compose file. Plex exposes web UI for status. Structured JSON logging via Docker daemon config (already set up in F1.2). Full Grafana/InfluxDB monitoring deferred to Phase 8 (Network Monitoring). |

**Post-Phase 1 Re-check**: All gates still PASS. No violations introduced during design.

## Project Structure

### Documentation (this feature)

```text
specs/004-plex-migration/
├── plan.md              # This file
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: infrastructure components and state transitions
├── quickstart.md        # Phase 1: step-by-step migration guide
└── tasks.md             # Phase 2: task breakdown (created by /speckit.tasks)
```

### Source Code (repository root)

```text
infrastructure/holygrail/
├── plex/
│   ├── docker-compose.yml       # Plex container with GPU, host networking
│   └── .env.example             # Template: PLEX_CLAIM, TZ, PUID, PGID
├── setup-nas-mounts.sh          # Configure NAS SMB mounts in fstab
└── verify-plex.sh               # Acceptance verification (FR-001 through FR-013)

scripts/
├── pi-status.sh                 # Update: reflect Pi's new role (Pi-hole only)
└── pi-update.sh                 # Update: if Pi role changes affect update targets

docs/
├── INFRASTRUCTURE.md            # Update: HOLYGRAIL services, Pi role, Emby retirement
└── F2.1-plex-migration.md       # Update: status to completed
```

**Structure Decision**: Follows the existing infrastructure/holygrail/ convention established in F1.1/F1.2. Each service stack gets its own subdirectory with a docker-compose.yml (per Constitution III). Setup scripts live at the holygrail/ level alongside existing post-install.sh and verify-*.sh scripts.

## Complexity Tracking

> No constitution violations. Table not needed.
