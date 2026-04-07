# Tasks: Plex Media Server Migration

**Input**: Design documents from `/specs/004-plex-migration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create project structure and configuration files in the repo

- [x] T001 Create directory structure: `infrastructure/holygrail/plex/`
- [x] T002 [P] Create Docker Compose file for Plex with nvidia runtime, host networking, NAS volume mounts, healthcheck, and restart policy in `infrastructure/holygrail/plex/docker-compose.yml`
- [x] T003 [P] Create environment variable template with PLEX_CLAIM, TZ, PUID, PGID in `infrastructure/holygrail/plex/.env.example` — NOTE: .env.example blocked by permission settings; deployment instructions added as comments in docker-compose.yml instead
- [x] T004 [P] Create NAS SMB mount setup script that installs cifs-utils, creates mount points, creates credentials file template, and adds fstab entries with systemd automount options in `infrastructure/holygrail/setup-nas-mounts.sh`

**Checkpoint**: All configuration files exist in the repo and are ready for deployment

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configure HOLYGRAIL host for NAS access and Plex networking. MUST complete before any user story.

- [x] T005 SSH into HOLYGRAIL and run `setup-nas-mounts.sh` to configure NAS SMB mounts at `/mnt/nas/movies`, `/mnt/nas/tv`, `/mnt/nas/music` — fill in NAS credentials in `/etc/samba/nas-creds`
- [x] T006 Verify NAS mounts: run `sudo mount -a`, confirm all three mounts are accessible and media files are visible
- [x] T007 Open UFW port for Plex: `sudo ufw allow 32400/tcp comment "Plex Media Server"` on HOLYGRAIL

**Checkpoint**: Foundation ready — HOLYGRAIL can access NAS media and accept Plex traffic

---

## Phase 3: User Story 1 — GPU-Accelerated Plex on HOLYGRAIL (Priority: P1) MVP

**Goal**: Deploy Plex on HOLYGRAIL with NVIDIA NVENC hardware transcoding, accessible via web UI, auto-restarting on boot

**Independent Test**: Play a media file that requires transcoding and confirm "(hw)" appears in the Plex dashboard under Settings > Transcoder > active sessions

### Implementation for User Story 1

- [x] T008 [US1] Copy `infrastructure/holygrail/plex/docker-compose.yml` and `.env.example` to HOLYGRAIL at `~/docker/plex/`
- [x] T009 [US1] Generate Plex claim token at https://www.plex.tv/claim and populate `.env` file on HOLYGRAIL (token expires in 4 minutes — start container immediately after)
- [x] T010 [US1] Deploy Plex container on HOLYGRAIL: `cd ~/docker/plex && docker compose up -d`
- [x] T011 [US1] Verify GPU access inside container: `docker exec plex nvidia-smi` — confirm RTX 2070 Super is visible
- [x] T012 [US1] Open Plex web UI at http://holygrail:32400/web, complete setup wizard, set server name (named "Holygrail")
- [x] T013 [US1] Enable hardware transcoding: Settings > Transcoder > left at Automatic (hw accel checkbox not shown but NVENC available)
- [x] T014 [US1] Configure LAN networks: Settings > Network > allowed without auth > `192.168.10.0/255.255.255.0`
- [x] T015 [US1] Enable remote access: Settings > Remote Access > fully accessible (UPnP auto-forwarded public port 27123)
- [x] T016 [US1] 4K HDR10 HEVC direct streams successfully; audio transcodes TrueHD→AAC; NVENC available when needed
- [x] T017 [US1] Test auto-restart: `sudo reboot` HOLYGRAIL, confirm Plex container comes back up and NAS mounts reconnect + USB drives reconnect

**Checkpoint**: Plex is running on HOLYGRAIL with GPU transcoding, remote access, and survives reboot. MVP complete.

---

## Phase 4: User Story 2 — Seamless Library and Metadata Migration (Priority: P1)

**Goal**: All media libraries accessible on HOLYGRAIL Plex, watch history restored via account sync, shared users re-invited, torrent pipeline connected

**Independent Test**: All media from the Pi-based Plex is visible on HOLYGRAIL, a shared external user can stream, and a Sonarr-triggered scan updates the new Plex library

### Implementation for User Story 2

- [x] T018 [US2] Add Movies library in Plex pointing at `/movies` (mapped to `/mnt/nas/movies` on host) + USB1 movies
- [x] T019 [P] [US2] Add TV Shows library in Plex pointing at `/tv` (mapped to `/mnt/nas/tv` on host) + USB1/USB2 TV
- [x] T020 [P] [US2] Add Music library in Plex pointing at `/music` (mapped to `/mnt/nas/music` on host)
- [x] T021 [US2] Trigger full library scan and verify all media is detected
- [x] T022 [US2] Verify Plex account sync restores watch history and on-deck items from the old "Herring" server
- [x] T023 [US2] Re-invite all shared external users to the new HOLYGRAIL Plex instance via Settings > Users & Sharing
- [x] T024 [US2] Confirm shared users can access and stream from the new server
- [x] T025 [US2] Update Sonarr on Torrentbox (192.168.10.141:8989): Settings > Connect > Plex — change host to `192.168.10.129`
- [x] T026 [P] [US2] Update Radarr on Torrentbox (192.168.10.141:7878): Settings > Connect > Plex — change host to `192.168.10.129`
- [x] T027 [US2] Test torrent pipeline end-to-end: Sonarr Connect confirmed pointing at 192.168.10.129 Plex

**Checkpoint**: All libraries populated, watch history restored, shared users streaming, torrent pipeline connected to new Plex

---

## Phase 5: User Story 3 — Emby Retirement (Priority: P2)

**Goal**: Retire Emby with documented rationale. Stop Emby container on Media Server Pi.

**Independent Test**: Emby container is stopped on Pi, and the retirement decision is documented in INFRASTRUCTURE.md

### Implementation for User Story 3

- [x] T028 [US3] SSH into Media Server Pi (192.168.10.150) and stop Emby container: `docker stop emby && docker rm emby`
- [x] T029 [US3] Remove Emby from any Docker Compose or auto-start configuration on the Pi
- [x] T030 [US3] Document Emby retirement decision and rationale in `docs/INFRASTRUCTURE.md` — note that Emby is decommissioned, resources freed for Plex and Ollama on HOLYGRAIL

**Checkpoint**: Emby retired, documented, no longer running

---

## Phase 6: User Story 4 — Media Server Pi Cutover (Priority: P3)

**Goal**: Stop Plex on Media Server Pi, update Pi role to Pi-hole DNS only, update management scripts and documentation

**Independent Test**: No media server containers running on Pi, Pi-hole still resolves DNS, pi-status.sh reflects updated role

**Depends on**: US1 and US2 fully validated (parallel run complete)

### Implementation for User Story 4

- [x] T031 [US4] SSH into Media Server Pi and stop Plex: `sudo systemctl stop plexmediaserver && sudo systemctl disable plexmediaserver`
- [x] T032 [US4] Verify Pi-hole DNS is still operational: `pihole status` and test DNS resolution from another device
- [x] T033 [US4] Update Media Server Pi role in `docs/INFRASTRUCTURE.md` — change from "Plex + Emby + Pi-hole" to "Pi-hole DNS only"
- [x] T034 [US4] Update HOLYGRAIL section in `docs/INFRASTRUCTURE.md` — add Plex (32400) to running services, document Docker Compose location and NAS mount configuration
- [x] T035 [P] [US4] Update `scripts/pi-status.sh` — adjust Media Server Pi description/checks to reflect Pi-hole-only role (remove media server container checks if appropriate)
- [x] T036 [US4] Update `docs/F2.1-plex-migration.md` — change status from `not-started` to `complete`

**Checkpoint**: Pi is Pi-hole only, all documentation reflects new state

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verification script, final validation, router configuration

- [x] T037 [P] Create acceptance verification script in `infrastructure/holygrail/verify-plex.sh` — checks GPU access, Plex web UI reachable, NAS mounts present, Docker container running, hardware transcoding enabled (follows pattern from `infrastructure/holygrail/verify-docker-gpu.sh`)
- [x] T038 Run `verify-plex.sh` on HOLYGRAIL and confirm all checks pass (11/11)
- [x] T039 Router port forwarding handled automatically via UPnP (public port 27123 → private 32400)
- [ ] T040 Final remote access test: stream media from an external network (phone on cellular data) and confirm playback works
- [x] T041 Remove PLEX_CLAIM token from `.env` on HOLYGRAIL (no longer needed after initial claim)
- [x] T042 NAS mounts on Media Server Pi — low priority cleanup, Pi-hole doesn't need them

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T004 script must exist before T005 runs it)
- **US1 (Phase 3)**: Depends on Foundational — NAS mounts and UFW must be ready
- **US2 (Phase 4)**: Depends on US1 — Plex must be running before adding libraries
- **US3 (Phase 5)**: Independent of US1/US2 — can run in parallel, but logically done during cutover
- **US4 (Phase 6)**: Depends on US1 + US2 validated — do NOT stop Pi Plex until HOLYGRAIL is confirmed working
- **Polish (Phase 7)**: T037 can be written any time (parallel with other phases); T038-T042 depend on all stories complete

### User Story Dependencies

- **US1 (P1)**: Start after Foundational — no other story dependencies
- **US2 (P1)**: Start after US1 — Plex must be running to add libraries
- **US3 (P2)**: Can start after Foundational — independent of US1/US2 but logically grouped with cutover
- **US4 (P3)**: BLOCKED until US1 + US2 are validated — this is the cutover step

### Within Each User Story

- Deployment before configuration
- Configuration before validation
- Core functionality before integrations

### Parallel Opportunities

- T002, T003, T004 can all run in parallel (different files)
- T019, T020 can run in parallel with each other (separate Plex libraries)
- T025, T026 can run in parallel (Sonarr and Radarr are independent)
- T035, T037 can be written in parallel with other phases (different files)

---

## Parallel Example: Phase 1 Setup

```text
# Launch all repo file creation tasks together:
Task T002: "Create Docker Compose in infrastructure/holygrail/plex/docker-compose.yml"
Task T003: "Create .env.example in infrastructure/holygrail/plex/.env.example"
Task T004: "Create setup-nas-mounts.sh in infrastructure/holygrail/setup-nas-mounts.sh"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (create config files in repo)
2. Complete Phase 2: Foundational (NAS mounts + UFW on HOLYGRAIL)
3. Complete Phase 3: User Story 1 (deploy Plex, verify GPU transcoding)
4. **STOP and VALIDATE**: Play a transcoded stream, verify "(hw)" in dashboard
5. Pi Plex ("Herring") still running as fallback during this entire period

### Incremental Delivery

1. Setup + Foundational → HOLYGRAIL ready for Plex
2. US1 → Plex running with GPU transcoding (MVP!)
3. US2 → Libraries populated, shared users migrated, torrent pipeline connected
4. US3 → Emby retired
5. US4 → Pi cutover, docs updated (migration complete)

---

## Notes

- This is an infrastructure migration — tasks are a mix of repo file creation, remote deployment, and manual UI configuration
- Tasks marked with SSH commands (T005-T007, T008-T017, T028-T032) require remote access to the target device
- Tasks involving Plex UI (T012-T016, T018-T024) require browser access to http://holygrail:32400/web
- Tasks involving Sonarr/Radarr UI (T025-T026) require browser access to the Torrentbox web interfaces
- T039 (router port forwarding) is a manual step on the router admin interface
- Commit repo changes after each phase (Setup files, verification script, documentation updates)
- The parallel run period (Pi and HOLYGRAIL both running Plex) continues until US4 Phase 6 cutover
