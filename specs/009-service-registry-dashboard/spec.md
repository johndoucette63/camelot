# Feature Specification: Service Registry & Health Dashboard

**Feature Branch**: `009-service-registry-dashboard`  
**Created**: 2026-04-09  
**Status**: Draft  
**Input**: User description: "@docs/F4.3-service-registry.md"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View All Local Containers (Priority: P1)

As a Camelot admin, I open the advisor dashboard and immediately see every Docker container running on HOLYGRAIL — name, image, status, ports, and uptime — without having to SSH into the machine or open Portainer.

**Why this priority**: The local host (HOLYGRAIL) is the most critical node; knowing its container state is the minimum viable use case and unblocks all other stories.

**Independent Test**: Can be fully tested by visiting the dashboard and confirming that containers known to be running on HOLYGRAIL appear in the list with correct metadata.

**Acceptance Scenarios**:

1. **Given** HOLYGRAIL has running containers, **When** the admin loads the dashboard, **Then** each running container is listed with its name, image, status, exposed ports, and uptime.
2. **Given** some containers on HOLYGRAIL are stopped or exited, **When** the admin views the dashboard, **Then** those containers appear in a separate "Stopped" section, distinct from running containers.
3. **Given** the dashboard was loaded 60 seconds ago, **When** a new container is started on HOLYGRAIL, **Then** it appears in the list within the next auto-refresh cycle (≤ 60 seconds).

---

### User Story 2 - Check Service Health Status (Priority: P2)

As a Camelot admin, I want each known service probed on a regular interval so the dashboard shows me at a glance whether a service is healthy, degraded, or unreachable — without me having to manually ping anything.

**Why this priority**: Container presence alone doesn't prove a service is responding; health checks surface real outages and deliver the core monitoring value.

**Independent Test**: Can be tested by intentionally stopping a known service (e.g., Plex) and confirming the dashboard transitions from green to red within the next check cycle.

**Acceptance Scenarios**:

1. **Given** a service passes its HTTP or TCP check, **When** the dashboard displays it, **Then** its status indicator is green.
2. **Given** a service responds but takes longer than the degraded threshold, **When** the dashboard displays it, **Then** its status indicator is yellow.
3. **Given** a service is unreachable (no response), **When** the check runs, **Then** its status indicator turns red.
4. **Given** health check results have been collected over time, **When** the admin clicks a service, **Then** they see a history of recent health check results (timestamp + status).

---

### User Story 3 - At-a-Glance System Health Summary (Priority: P2)

As a Camelot admin, I want the top of the dashboard to show an overall health summary — something like "12 / 14 services healthy" — so I can immediately tell whether anything needs attention.

**Why this priority**: The summary is the fastest path to situational awareness; it turns the dashboard into an effective at-a-glance tool rather than requiring the admin to scan every row.

**Independent Test**: Can be tested by marking one service as down and confirming the summary count changes accordingly.

**Acceptance Scenarios**:

1. **Given** all services are healthy, **When** the admin views the dashboard header, **Then** the summary reads "N / N services healthy."
2. **Given** one service is red, **When** the admin views the dashboard header, **Then** the summary reflects the reduced healthy count.
3. **Given** the admin clicks a service row, **When** the detail view opens, **Then** they see name, host, port, status, last check time, and recent health history.

---

### User Story 4 - Monitor Remote Pi Services (Priority: P3)

As a Camelot admin, I want services running on Torrentbox, the NAS, and other Pis to appear in the same dashboard — grouped by host — so the entire network is covered in one place.

**Why this priority**: Remote hosts are monitored via simple port/HTTP checks (no Docker socket needed), so this extends coverage at low risk once local monitoring works.

**Independent Test**: Can be tested by adding a remote service definition for Deluge on Torrentbox and confirming it appears in the dashboard grouped under "Torrentbox."

**Acceptance Scenarios**:

1. **Given** remote service definitions exist for Torrentbox (Deluge, Sonarr, Radarr, Prowlarr) and NAS (SMB, Pi-hole), **When** the admin views the dashboard, **Then** those services are listed under their respective host sections.
2. **Given** the network route to a remote host is down, **When** health checks are attempted, **Then** the dashboard shows a host-level alert rather than individual service failures.
3. **Given** a service definition is added or removed in the configuration, **When** the advisor is restarted or reloaded, **Then** the dashboard reflects the updated service list.

---

### Edge Cases

- When the Docker socket is temporarily unavailable on HOLYGRAIL, the dashboard shows the last known container state with a staleness warning banner on the HOLYGRAIL section; it does not hide or blank the section.
- How does the system handle a service that was healthy, becomes red, then recovers — does history show the full transition?
- What if a port check succeeds but the HTTP health endpoint returns a non-200 status?
- What happens when a remote host's hostname cannot be resolved?
- Docker guarantees unique container names per host. If a container's name is ambiguous in the UI, the short container ID (first 12 chars) is shown alongside the name for disambiguation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST enumerate all Docker containers on HOLYGRAIL and display each container's name, image, status, exposed ports, and uptime. Container discovery is inventory-only; discovered containers are not automatically enrolled in health checks.
- **FR-002**: System MUST separately display stopped or exited containers from running containers.
- **FR-003**: System MUST auto-refresh container and health data on a configurable interval, defaulting to 60 seconds.
- **FR-004**: System MUST perform health checks for each defined service using one of two check types: HTTP 200 response or TCP port reachability. TCP checks are binary (green/red only); yellow/degraded status applies to HTTP checks only (response time > 2 seconds).
- **FR-005**: System MUST assign a health status to each service: green (healthy), yellow (slow/degraded), red (down/unreachable).
- **FR-006**: System MUST persist health check results so that per-service health history is available for trend analysis.
- **FR-007**: System MUST display a summary at the top of the dashboard indicating the count of healthy services vs. total defined services.
- **FR-008**: System MUST present services grouped by host in the dashboard view.
- **FR-009**: System MUST display each service entry with: name, host, port, status indicator, and last check timestamp.
- **FR-010**: System MUST show health history and full details when a service entry is selected.
- **FR-011**: System MUST support defining remote service endpoints (host, port, check type) for Pis and other network devices via configuration file or database seed; no dashboard UI for managing service definitions is required.
- **FR-012**: System MUST display a host-level alert when a remote host is entirely unreachable, rather than marking each individual service as down.
- **FR-013**: System MUST include health checks for Torrentbox services (Deluge, Sonarr, Radarr, Prowlarr), NAS services (SMB), and Pi-hole DNS services (Pi-hole) as default remote definitions.
- **FR-014**: When the Docker socket on HOLYGRAIL is unavailable, the system MUST display the last successfully retrieved container state alongside a visible staleness warning; it MUST NOT hide or blank the container section.

### Key Entities

- **Service Definition**: A configured entry representing a known service — attributes include name, host, port, check type (HTTP/TCP), check interval, and degraded threshold.
- **Container Record**: A discovered Docker container — attributes include name, image, status, exposed ports, uptime, and host origin.
- **Health Check Result**: A timestamped record of a single probe — attributes include service reference, timestamp, status (green/yellow/red), and response time or error message.
- **Host**: A network node (HOLYGRAIL, Torrentbox, NAS, Pi-hole DNS) that owns one or more services; carries reachability state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The admin can determine the health status of any monitored service within 60 seconds of a state change occurring.
- **SC-002**: The dashboard loads and displays all services in under 3 seconds under normal network conditions.
- **SC-003**: 100% of Docker containers running on HOLYGRAIL at check time appear in the dashboard after an auto-refresh.
- **SC-004**: Health history is retained for a minimum of 24 hours and a maximum of 7 days; results older than 7 days are automatically purged.
- **SC-005**: The overall health summary is visible without scrolling on a standard 1080p display.
- **SC-006**: An admin with no prior training can identify all red/yellow services and navigate to their details within 2 minutes of opening the dashboard.

## Clarifications

### Session 2026-04-09

- Q: How are service definitions managed? → A: Config/seed only — definitions managed in a file or DB seed, no dashboard UI.
- Q: When the Docker socket on HOLYGRAIL is unavailable, what does the dashboard show? → A: Last known container state with a staleness warning banner; section is not hidden.
- Q: Are discovered Docker containers automatically health-checked, or separate from service definitions? → A: Separate tracks — containers are inventory only; health checks run only against explicitly defined services.
- Q: What is the maximum health history retention period? → A: 7 days.
- Q: Do TCP checks support a yellow/degraded status? → A: No — TCP is binary; green (port open) or red (unreachable only).

## Assumptions

- The Docker socket on HOLYGRAIL is accessible to the advisor backend container (mounted as a volume).
- Remote Pi services are reachable via TCP/HTTP from HOLYGRAIL on the `192.168.10.0/24` network; no VPN tunnel is required for health checks.
- The degraded (yellow) threshold applies to HTTP checks only: response time > 2 seconds is considered degraded. TCP checks are binary (green/red); there is no yellow state for TCP.
- SMB health checks use a TCP port-open check on port 445 (full SMB protocol negotiation is out of scope).
- Pi-hole health check uses an HTTP check against the Pi-hole admin web interface.
- Service definitions are stored in the advisor's existing PostgreSQL database and can be seeded via a migration or config file.
- Mobile/responsive support is out of scope for v1; the dashboard targets desktop browsers.
- Authentication for the advisor dashboard is already handled by the existing advisor app (F4.1 dependency).
