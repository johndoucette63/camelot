# Tasks: Monitoring Migration & Traefik Reverse Proxy

**Input**: Design documents from `/specs/005-monitoring-traefik-migration/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Not requested. Verification scripts are included as US3 deliverables (post-deployment validation, per Constitution IV: Test-After).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory structure, environment templates, and shared Docker network configuration

- [x] T001 Create directory structure: `infrastructure/holygrail/monitoring/` and `infrastructure/holygrail/traefik/config/`
- [x] T002 [P] Create monitoring stack `.env.example` with `GRAFANA_ADMIN_PASSWORD`, `INFLUXDB_ADMIN_PASSWORD`, `INFLUXDB_USER`, `INFLUXDB_USER_PASSWORD`, and `TZ` variables in `infrastructure/holygrail/monitoring/.env.example`
- [x] T003 [P] Create Traefik `.env.example` with `TRAEFIK_LOG_LEVEL` (default: ERROR) and `TZ` variables in `infrastructure/holygrail/traefik/.env.example`. Traefik dashboard is unauthenticated (LAN-only per Constitution I), so no dashboard credentials needed.
- [x] T004 [P] Add `.env` to `.gitignore` for infrastructure directories — ensure `infrastructure/holygrail/monitoring/.env` and `infrastructure/holygrail/traefik/.env` are gitignored

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Update shared monitoring configs that MUST be correct before any HOLYGRAIL deployment

**CRITICAL**: These config changes affect the monitoring stack and Traefik routing. Must complete before US1 deployment.

- [x] T005 Update Smokeping Targets: rename "Plex" entry to "HOLYGRAIL", change IP from `192.168.10.150` to `192.168.10.129`, add HOLYGRAIL as named infrastructure target in `infrastructure/monitoring/smokeping/Targets`
- [x] T006 [P] Update Grafana InfluxDB datasource URL from `http://host.docker.internal:8086` to `http://influxdb:8086` in `infrastructure/monitoring/grafana/provisioning/datasources/influxdb.yml`

**Checkpoint**: Shared configs updated — HOLYGRAIL deployment can begin

---

## Phase 3: User Story 1 - Deploy Monitoring Stack on HOLYGRAIL (Priority: P1) MVP

**Goal**: Grafana, InfluxDB 1.8, Smokeping, Smokeping exporter, and speedtest running as Docker containers on HOLYGRAIL, accessible on their expected ports from the LAN.

**Independent Test**: Deploy the stack on HOLYGRAIL and confirm each service responds — `curl http://192.168.10.129:3000/api/health` (Grafana), `curl http://192.168.10.129:8086/ping` (InfluxDB), `curl http://192.168.10.129:8080` (Smokeping).

### Implementation for User Story 1

- [x] T007 [US1] Create monitoring `docker-compose.yml` with InfluxDB 1.8, Grafana, Smokeping, Smokeping exporter, and speedtest services in `infrastructure/holygrail/monitoring/docker-compose.yml`. Must include: `monitoring` internal network, `holygrail-proxy` external network, named Docker volumes for persistent data, healthchecks on all services — Grafana/Smokeping/InfluxDB via HTTP, exporter and speedtest via process-alive checks (e.g., `pgrep -f python`), `restart: unless-stopped` on all services, environment variables referencing `.env` file. InfluxDB must auto-create `network_metrics` database via `INFLUXDB_DB` env var. Grafana `GF_SERVER_ROOT_URL` set to `http://grafana.holygrail`. Exporter and speedtest connect to `influxdb:8086` via Docker network (not `host.docker.internal`). Mount Smokeping Targets, Grafana dashboards, and provisioning configs from `infrastructure/monitoring/` paths. Deployment prerequisite: `docker network create holygrail-proxy` must be run on HOLYGRAIL before `docker compose up` (see quickstart.md Step 1).

**Checkpoint**: Monitoring stack deployable on HOLYGRAIL. All five services respond on expected ports. Grafana dashboard shows live data within 10 minutes. This is the MVP — monitoring works without Traefik.

---

## Phase 4: User Story 2 - Deploy Traefik Reverse Proxy (Priority: P2)

**Goal**: Traefik routes hostname requests (`*.holygrail`) to the correct HOLYGRAIL backend service. All services accessible via clean names from the Mac.

**Independent Test**: Navigate to `grafana.holygrail`, `smokeping.holygrail`, `plex.holygrail`, `portainer.holygrail`, and `traefik.holygrail` from the Mac — all load without port numbers.

### Implementation for User Story 2

- [x] T008 [US2] Create Traefik `docker-compose.yml` with Docker provider (for label-based routing) and file provider (for host-network services) in `infrastructure/holygrail/traefik/docker-compose.yml`. Must include: `holygrail-proxy` external network, Docker socket mount (read-only), port 80 for HTTP entrypoint, Traefik dashboard enabled on port 8080 or via hostname, `restart: unless-stopped`, healthcheck. Configure Traefik to watch Docker labels on the `holygrail-proxy` network and load `config/dynamic.yml` as file provider.
- [x] T009 [P] [US2] Create Traefik dynamic config with file-provider route for Plex (`plex.holygrail` → `http://192.168.10.129:32400`) in `infrastructure/holygrail/traefik/config/dynamic.yml`. Plex uses host network mode so cannot use Docker labels — this static route is the workaround per research R-003.
- [x] T010 [US2] Add Traefik Docker labels for hostname routing to monitoring services (Grafana → `grafana.holygrail`, Smokeping → `smokeping.holygrail`) and ensure `holygrail-proxy` external network is declared in `infrastructure/holygrail/monitoring/docker-compose.yml`
- [x] T011 [P] [US2] Update Portainer compose: add `holygrail-proxy` external network and Traefik labels for `portainer.holygrail` routing (note: Portainer uses HTTPS on 9443, configure Traefik `serversTransport` for HTTPS backend) in `infrastructure/holygrail/docker/portainer-compose.yml`
- [x] T012 [US2] Create Mac `/etc/hosts` setup helper script that appends all `*.holygrail` hostname entries pointing to `192.168.10.129` in `scripts/setup-holygrail-dns.sh`. Include: idempotency check (don't add duplicates), list of hostnames (grafana, smokeping, plex, portainer, traefik), `sudo` usage for `/etc/hosts` modification.

**Checkpoint**: All HOLYGRAIL services accessible via `*.holygrail` hostnames from Mac. Traefik dashboard shows healthy routes. Direct `IP:port` access still works as fallback.

---

## Phase 5: User Story 3 - Verify Monitoring Continuity (Priority: P3)

**Goal**: Confirm all monitoring data flows correctly on HOLYGRAIL — Smokeping targets report data, speedtest results accumulate, Grafana dashboards render live data.

**Independent Test**: Run verification scripts after stack has been up for 10+ minutes. All checks pass.

### Implementation for User Story 3

- [x] T013 [US3] Create deployment verification script that checks all monitoring services respond on expected ports (Grafana health API, InfluxDB ping, Smokeping HTTP), verifies InfluxDB `network_metrics` database exists, and confirms Smokeping targets are collecting data in `scripts/verify-monitoring.sh`. Include a `--reboot-test` flag that SSHs to HOLYGRAIL, triggers `sudo reboot`, waits 3 minutes, then re-runs all service checks to validate SC-006 (auto-recovery).
- [x] T014 [P] [US3] Create Traefik route verification script that tests all `*.holygrail` hostnames resolve and return HTTP 200 from the Mac workstation in `scripts/verify-traefik-routes.sh`

**Checkpoint**: Verification scripts confirm end-to-end data flow. All Grafana panels render live data. HOLYGRAIL monitoring is production-ready.

---

## Phase 6: User Story 4 - Update Infrastructure Documentation (Priority: P4)

**Goal**: Repository documentation accurately reflects the live infrastructure with HOLYGRAIL as the monitoring host and Traefik providing hostname routing.

**Independent Test**: Read INFRASTRUCTURE.md and confirm Grafana, InfluxDB, Smokeping listed under HOLYGRAIL, Traefik documented with all routes, no references to Torrentbox as monitoring host.

### Implementation for User Story 4

- [x] T015 [US4] Update INFRASTRUCTURE.md: move Grafana (3000), InfluxDB (8086), Smokeping (8080) from Torrentbox to HOLYGRAIL in the service locations table. Add Traefik (80) to HOLYGRAIL services. Add `*.holygrail` hostname URL column or section in `docs/INFRASTRUCTURE.md`
- [x] T016 [P] [US4] Archive old Torrentbox monitoring `docker-compose.yml`: add deprecation header comment noting services migrated to HOLYGRAIL, and move or clearly mark as archived in `infrastructure/monitoring/docker-compose.yml`
- [x] T017 [US4] Update CLAUDE.md active technologies section to reflect monitoring migration deliverables (Traefik, Grafana on HOLYGRAIL, InfluxDB 1.8 containerized) in `CLAUDE.md`

**Checkpoint**: Repo is the single source of truth for infrastructure state. No stale references to Torrentbox monitoring.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and consistency checks

- [x] T018 [P] Run quickstart.md end-to-end validation (manual — requires live HOLYGRAIL deployment): follow all deployment steps from quickstart.md on HOLYGRAIL and verify each checkpoint passes
- [x] T019 Review all compose files for consistency: verify all services have `restart: unless-stopped`, healthchecks, `holygrail-proxy` network where needed, and no hardcoded credentials

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — core monitoring stack
- **US2 (Phase 4)**: Depends on US1 — Traefik needs backend services to route to
- **US3 (Phase 5)**: Depends on US1 and US2 — verification requires deployed services
- **US4 (Phase 6)**: Can start after US1, fully completes after US2/US3
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories. This is the MVP.
- **User Story 2 (P2)**: Depends on US1 — Traefik needs monitoring services running to route to them. Also modifies `infrastructure/holygrail/monitoring/docker-compose.yml` (adding labels).
- **User Story 3 (P3)**: Depends on US1 and US2 — verification scripts test both monitoring services and Traefik routes.
- **User Story 4 (P4)**: Partially parallel with US2/US3 — documentation updates for US1 can start immediately, but full completion requires knowledge of all deployed services.

### Within Each User Story

- Config files before compose files
- Compose files before verification scripts
- Core implementation before integration (e.g., Traefik compose before Traefik labels on monitoring)

### Parallel Opportunities

- T002, T003, T004 can all run in parallel (different files, setup phase)
- T005 and T006 can run in parallel (different config files, foundational phase)
- T009 and T011 can run in parallel within US2 (different files)
- T013 and T014 can run in parallel within US3 (different scripts)
- T015 and T016 can run in parallel within US4 (different files)
- T018 and T019 can run in parallel (polish phase)

---

## Parallel Example: Phase 1 Setup

```bash
# Launch all setup tasks together:
Task: "Create .env.example for monitoring in infrastructure/holygrail/monitoring/.env.example"
Task: "Create .env.example for Traefik in infrastructure/holygrail/traefik/.env.example"
Task: "Add .env to .gitignore for infrastructure directories"
```

## Parallel Example: User Story 2

```bash
# After T008 (Traefik compose) is complete, launch in parallel:
Task: "Create Traefik dynamic config for Plex in infrastructure/holygrail/traefik/config/dynamic.yml"
Task: "Update Portainer compose with Traefik labels in infrastructure/holygrail/docker/portainer-compose.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T006)
3. Complete Phase 3: User Story 1 (T007)
4. **STOP and VALIDATE**: Deploy on HOLYGRAIL, verify all 5 services respond on expected ports, check Grafana dashboard loads with live data
5. Monitoring is centralized — this alone delivers significant value

### Incremental Delivery

1. Complete Setup + Foundational → Configs ready
2. Add User Story 1 → Deploy monitoring → Validate (MVP!)
3. Add User Story 2 → Deploy Traefik → Validate clean URLs
4. Add User Story 3 → Run verification scripts → Confirm continuity
5. Add User Story 4 → Update docs → Repo matches reality
6. Each story adds value without breaking previous stories

### Single Developer Strategy (Camelot)

Since this is a single-admin project:
1. Work sequentially through phases: Setup → Foundational → US1 → US2 → US3 → US4 → Polish
2. Use parallel task markers [P] to batch file creation within each phase
3. Deploy and verify at each checkpoint before proceeding

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- This is an infrastructure project — "implementation" means writing Docker Compose YAML, shell scripts, and config files
- No application tests requested; US3 verification scripts serve as post-deployment validation per Constitution IV (Test-After)
- Commit after each task or logical group
- Stop at any checkpoint to validate independently
- Direct `IP:port` access remains as fallback even after Traefik deployment
