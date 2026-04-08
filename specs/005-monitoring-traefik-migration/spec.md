# Feature Specification: Monitoring Migration & Traefik Reverse Proxy

**Feature Branch**: `005-monitoring-traefik-migration`  
**Created**: 2026-04-08  
**Status**: Draft  
**Input**: User description: "Migrate monitoring stack (Grafana, InfluxDB, Smokeping) to HOLYGRAIL and deploy Traefik reverse proxy for clean service URLs"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deploy Monitoring Stack on HOLYGRAIL (Priority: P1)

As the Camelot admin, I need Grafana, InfluxDB, and Smokeping running on HOLYGRAIL so that monitoring is centralized on the most capable machine instead of consuming resources on the Torrentbox Pi. This is the foundation everything else depends on — Traefik routes to these services, and the future AI pipeline (Phase 3+) consumes this data.

**Why this priority**: Without the monitoring services running on HOLYGRAIL, nothing else in this feature works. This is the core migration that unblocks Traefik routing, monitoring continuity verification, and downstream AI features.

**Independent Test**: Deploy the monitoring Docker Compose stack on HOLYGRAIL and confirm each service responds on its expected port from the local network.

**Acceptance Scenarios**:

1. **Given** HOLYGRAIL is running with Docker installed, **When** the monitoring Docker Compose stack is deployed, **Then** Grafana is accessible on port 3000, InfluxDB on port 8086, and Smokeping on port 8080 from any device on the LAN.
2. **Given** the monitoring stack is running on HOLYGRAIL, **When** the admin opens Grafana and navigates to dashboards, **Then** the existing network-monitoring dashboard is available with all panels intact (latency overview, speedtest speeds, packet loss, per-target latency).
3. **Given** the Smokeping exporter is running, **When** 5 minutes have elapsed after deployment, **Then** new latency data points appear in InfluxDB and are visible in Grafana.
4. **Given** the speedtest service is configured, **When** 30 minutes have elapsed, **Then** at least one new speedtest result is recorded in InfluxDB.

---

### User Story 2 - Deploy Traefik Reverse Proxy (Priority: P2)

As the Camelot admin, I want a reverse proxy so I can access all HOLYGRAIL services via clean hostnames (e.g., `grafana.holygrail`, `plex.holygrail`, `smokeping.holygrail`) instead of remembering IP addresses and port numbers.

**Why this priority**: Clean URLs improve daily usability for every service on HOLYGRAIL. This depends on P1 services being deployed first, and it establishes the routing layer that all future HOLYGRAIL services (Ollama, Network Advisor) will also use.

**Independent Test**: Deploy Traefik, configure hostname routing, and confirm services are reachable via their subdomain names from the Mac workstation.

**Acceptance Scenarios**:

1. **Given** Traefik is deployed on HOLYGRAIL, **When** the admin navigates to `grafana.holygrail` in a browser on the Mac, **Then** the Grafana UI loads without specifying a port number.
2. **Given** Traefik is deployed, **When** the admin navigates to `plex.holygrail`, **Then** the Plex Web UI loads.
3. **Given** Traefik is deployed, **When** the admin navigates to `smokeping.holygrail`, **Then** the Smokeping UI loads.
4. **Given** Traefik is running, **When** the admin navigates to the Traefik dashboard URL, **Then** the dashboard displays all configured routes and their health status.
5. **Given** the Mac workstation needs DNS resolution for `*.holygrail` names, **When** the admin follows the documented setup steps, **Then** all service hostnames resolve correctly from the Mac.

---

### User Story 3 - Verify Monitoring Continuity (Priority: P3)

As the Camelot admin, I want to confirm that after migration, all monitoring data flows correctly with no gaps in visibility — latency tracking, speedtests, and dashboard rendering all work as they did on Torrentbox.

**Why this priority**: Migration without verification risks silent data loss. This story validates the P1 deployment is fully functional end-to-end before decommissioning the old stack on Torrentbox.

**Independent Test**: After the monitoring stack runs on HOLYGRAIL for at least one hour, verify that all Smokeping targets report data, speedtest results accumulate, and Grafana dashboards render live data with no broken panels.

**Acceptance Scenarios**:

1. **Given** Smokeping is running on HOLYGRAIL, **When** the admin views the Smokeping UI, **Then** latency data is being collected for all configured targets (infrastructure devices, external DNS, internet sites).
2. **Given** the Smokeping targets file has been updated, **When** the admin checks the target for the former "Plex" entry, **Then** it now points to HOLYGRAIL (192.168.10.129) instead of the old Media Server Pi (192.168.10.150).
3. **Given** the monitoring stack has been running for 1 hour, **When** the admin checks Grafana, **Then** all dashboard panels show live data with no "No data" or error states.
4. **Given** the old Torrentbox monitoring stack is still running in parallel, **When** the admin compares data from both stacks, **Then** HOLYGRAIL reports consistent latency values (within expected variance) for the same targets.

---

### User Story 4 - Update Infrastructure Documentation (Priority: P4)

As the Camelot admin, I want all repo documentation and Docker Compose files to reflect the new service locations so that the repository is the single source of truth for the live infrastructure.

**Why this priority**: Documentation accuracy prevents confusion in future maintenance and is required before the old Torrentbox monitoring configs can be archived. Lower priority because the migration works without updated docs.

**Independent Test**: Review all documentation files and confirm they accurately describe where each service runs, with no references to the old Torrentbox monitoring location.

**Acceptance Scenarios**:

1. **Given** the migration is complete, **When** the admin reads INFRASTRUCTURE.md, **Then** Grafana, InfluxDB, and Smokeping are listed under HOLYGRAIL (192.168.10.129), not Torrentbox.
2. **Given** per-stack HOLYGRAIL Docker Compose files exist, **When** the admin reads them, **Then** they collectively contain service definitions for Plex, Portainer, Grafana, InfluxDB, Smokeping, Smokeping exporter, speedtest, and Traefik, all connected via the shared holygrail-proxy network.
3. **Given** the old Torrentbox monitoring configs, **When** the admin checks the repo, **Then** they are archived or removed and no longer referenced as the active configuration.

---

### Edge Cases

- What happens if InfluxDB on HOLYGRAIL starts with an empty database — does the exporter and speedtest logger create the required database and measurements automatically on first write?
- What happens if a Smokeping target is unreachable during migration — does the exporter handle gaps gracefully without crashing?
- What happens if Traefik cannot reach a backend service — does it display a meaningful error page or a generic connection refused?
- How does the system behave if HOLYGRAIL's Docker engine restarts — do all monitoring and proxy services auto-recover without manual intervention?
- What happens if the Mac's `/etc/hosts` entries for `*.holygrail` become stale or are missing — can the admin still access services via direct `IP:port` as a fallback?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy Grafana, InfluxDB, Smokeping, Smokeping exporter, and speedtest logger as containerized services on HOLYGRAIL.
- **FR-002**: System MUST import the existing network-monitoring dashboard into Grafana with all panels functional (latency overview, speedtest speeds, packet loss, per-target latency).
- **FR-003**: System MUST configure Grafana's data source to connect to the HOLYGRAIL InfluxDB instance using the `network_metrics` database.
- **FR-004**: System MUST update Smokeping targets to reflect current device locations — specifically changing the Plex/Media Server target from 192.168.10.150 to HOLYGRAIL at 192.168.10.129.
- **FR-005**: System MUST run automated speedtest measurements on a recurring schedule (every 30 minutes) and store results in InfluxDB.
- **FR-006**: System MUST deploy Traefik as a reverse proxy on HOLYGRAIL, routing requests by hostname to the correct backend service.
- **FR-007**: System MUST provide hostname-based access to at minimum: Grafana, Smokeping, Plex, Portainer, and the Traefik dashboard itself.
- **FR-008**: System MUST provide documentation for configuring the Mac workstation to resolve `*.holygrail` hostnames to HOLYGRAIL's IP address.
- **FR-009**: System MUST ensure all monitoring and proxy services automatically restart after a HOLYGRAIL reboot.
- **FR-010**: System MUST produce per-stack Docker Compose configurations that collectively cover all HOLYGRAIL services (monitoring, media, and proxy), connected via a shared Docker network.
- **FR-011**: System MUST update INFRASTRUCTURE.md to reflect the new service locations, ports, and hostname URLs.
- **FR-012**: System MUST archive or remove the old Torrentbox monitoring Docker Compose and configs from the active infrastructure path.

### Key Entities

- **Monitoring Stack**: The collection of services (Grafana, InfluxDB, Smokeping, exporter, speedtest) that provide network observability. Currently on Torrentbox, migrating to HOLYGRAIL.
- **Reverse Proxy (Traefik)**: A service that maps clean hostnames to backend service ports, eliminating the need to remember port numbers. New addition to HOLYGRAIL.
- **Smokeping Targets**: The list of network devices and external hosts being monitored for latency and packet loss. Must be updated to reflect HOLYGRAIL's role as the central server.
- **Grafana Dashboards**: Pre-configured visualization panels showing network health metrics. Must be imported intact from the existing configuration.
- **Service Hostnames**: The `*.holygrail` DNS names that Traefik routes to backend services (e.g., `grafana.holygrail`, `plex.holygrail`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All five monitoring services (Grafana, InfluxDB, Smokeping, exporter, speedtest) are accessible on HOLYGRAIL within 2 minutes of stack deployment.
- **SC-002**: The network-monitoring dashboard in Grafana renders all panels with live data and zero "No data" errors within 10 minutes of deployment.
- **SC-003**: Smokeping collects latency data for 100% of configured targets (infrastructure devices and external hosts) within 5 minutes of startup.
- **SC-004**: All HOLYGRAIL services are accessible via their clean hostnames from the Mac workstation without specifying port numbers.
- **SC-005**: The Traefik dashboard shows healthy routing status for all configured service backends.
- **SC-006**: After a simulated HOLYGRAIL reboot, all monitoring and proxy services recover automatically within 3 minutes without manual intervention.
- **SC-007**: Speedtest measurements are recorded at least twice per hour in InfluxDB.
- **SC-008**: The repository documentation (INFRASTRUCTURE.md, Docker Compose files) accurately reflects the live infrastructure with no references to Torrentbox as the monitoring host.

## Assumptions

- HOLYGRAIL is already running Ubuntu 24.04 LTS with Docker Engine, Docker Compose v2, and NVIDIA drivers installed (Phase 1 complete).
- A fresh InfluxDB database on HOLYGRAIL is acceptable — historical data migration from Torrentbox is not required (fresh collection is sufficient per the feature doc).
- The Torrentbox monitoring stack will remain running in parallel during migration for comparison, and will be decommissioned separately after verification.
- The `*.holygrail` hostname scheme will use `/etc/hosts` entries on the Mac (not a DNS server change), since this is a single-admin LAN environment.
- Traefik will handle HTTP routing only (no TLS/HTTPS certificates) since all traffic is on the local LAN.
- Portainer (already deployed on HOLYGRAIL) will be included in the unified Docker Compose and get a Traefik hostname route.
- The existing Grafana dashboard JSON and provisioning configs in `infrastructure/monitoring/` are the canonical source for dashboard migration.
- The Smokeping exporter will use Docker networking on HOLYGRAIL (not `host.docker.internal` as on Torrentbox) since all services will be on the same Docker network.
