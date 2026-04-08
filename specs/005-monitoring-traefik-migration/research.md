# Research: Monitoring Migration & Traefik Reverse Proxy

**Feature Branch**: `005-monitoring-traefik-migration`  
**Date**: 2026-04-08

## R-001: Compose File Organization (Constitution Compliance)

**Decision**: Separate Docker Compose files per service stack, connected via a shared external Docker network.

**Rationale**: Constitution Principle III states: "Each service stack gets its own `docker-compose.yml` in the appropriate `infrastructure/` subdirectory." A unified compose file would violate this principle. The shared external network allows Traefik to discover and route to services across compose files.

**Alternatives considered**:
- Single unified `docker-compose.yml` for all HOLYGRAIL services — rejected, violates Constitution III.
- Fully isolated compose files with no shared network — rejected, Traefik cannot route to services it can't reach.

**Implementation**: Create a shared Docker network (`holygrail-proxy`) as an external network. Each compose file declares it under `networks:`. Traefik joins this network and routes via Docker labels on backend services.

**Note**: Spec FR-010 requests a "unified Docker Compose configuration." This will be implemented as per-stack compose files that collectively cover all services, satisfying the intent (all services tracked in repo) while honoring the constitution.

## R-002: InfluxDB Version and Containerization

**Decision**: Deploy InfluxDB 1.8 as a Docker container on HOLYGRAIL.

**Rationale**: The existing monitoring stack uses InfluxDB 1.x line protocol. The Grafana datasource, Smokeping exporter, and speedtest logger all use the 1.x client library (`influxdb>=5.3.1`). Migrating to InfluxDB 2.x would require rewriting all queries, datasource configs, and Python scripts for no immediate benefit. Version 1.8 is the final 1.x release with long-term community support.

**Alternatives considered**:
- InfluxDB 2.x — rejected, would require rewriting all existing integrations (exporter scripts, Grafana datasource, dashboard queries) with no functional gain for this use case.

**Implementation**: Use official `influxdb:1.8` Docker image. Create `network_metrics` database on first start via environment variables. Services connect via Docker network hostname `influxdb:8086` instead of `host.docker.internal:8086`.

## R-003: Traefik Routing for Host-Network Services (Plex)

**Decision**: Use Traefik's file provider to route to Plex, which runs in host network mode.

**Rationale**: Plex uses `network_mode: host` for DLNA/GDM discovery and direct client connections. Switching to bridge mode would break discovery features. Traefik's Docker provider cannot see host-network containers, so a static file-provider route is needed for Plex specifically. All other services use bridge networking with Docker labels.

**Alternatives considered**:
- Switch Plex to bridge mode — rejected, breaks DLNA discovery and requires extensive port mapping.
- Skip Traefik routing for Plex — rejected, defeats the purpose of clean URLs for all services.

**Implementation**: Traefik `dynamic.yml` file provider with a static route: `plex.holygrail` → `http://192.168.10.129:32400`. All other services use Docker labels on the shared `holygrail-proxy` network.

## R-004: DNS Resolution on Mac Workstation

**Decision**: Use individual `/etc/hosts` entries on the Mac for each `*.holygrail` hostname.

**Rationale**: macOS `/etc/hosts` does not support wildcard entries. Individual entries are the simplest approach for a single-admin LAN (Constitution II — simplest thing that works). The number of services is small (5-7 hostnames), so maintenance is minimal.

**Alternatives considered**:
- dnsmasq on Mac for wildcard `*.holygrail` resolution — rejected, adds a running service on the Mac (which is management-only per CLAUDE.md), and is overkill for <10 hostnames.
- Pi-hole custom DNS entries — considered viable but rejected for now; Pi-hole is on 192.168.10.150 (the old media server Pi whose future role is uncertain after monitoring migrates off Torrentbox). Can revisit when Pi roles stabilize.

**Implementation**: Document required `/etc/hosts` entries in a setup script or README. Provide a one-liner to append all entries. Fallback to direct `IP:port` access always works.

## R-005: Secrets Management

**Decision**: Use `.env` files (gitignored) for all credentials per Constitution III.

**Rationale**: Constitution states "Secrets MUST NOT be committed to the repo. Use `.env` files (gitignored) or Docker secrets." The existing Torrentbox compose hardcodes credentials in environment variables. The HOLYGRAIL deployment must use `.env` files with `.env.example` templates committed to the repo.

**Alternatives considered**:
- Docker secrets — rejected, adds unnecessary complexity for a single-admin system.
- Hardcoded in compose files — rejected, violates constitution.

**Implementation**: Create `.env.example` files for each compose stack documenting required variables. Actual `.env` files are gitignored. Variables: `GRAFANA_ADMIN_PASSWORD`, `INFLUXDB_ADMIN_PASSWORD`, `INFLUXDB_USER`, `INFLUXDB_USER_PASSWORD`.

## R-006: Smokeping Target Updates

**Decision**: Update Smokeping targets to reflect HOLYGRAIL as the central server.

**Rationale**: The current Targets file references Plex at 192.168.10.150 (old Media Server Pi). Plex has migrated to HOLYGRAIL (192.168.10.129). Additionally, the Torrentbox self-reference should be updated since monitoring no longer runs there. Add HOLYGRAIL as an infrastructure target.

**Changes required**:
- Rename "Plex" target from 192.168.10.150 to HOLYGRAIL at 192.168.10.129
- Add HOLYGRAIL as a named infrastructure target
- Review slow devices list for any stale entries

## R-007: Grafana Datasource and Dashboard Updates

**Decision**: Update Grafana provisioning to use Docker-internal InfluxDB hostname.

**Rationale**: On Torrentbox, Grafana connects to InfluxDB via `host.docker.internal:8086`. On HOLYGRAIL, InfluxDB runs in the same Docker network, so the datasource URL changes to `http://influxdb:8086`. The dashboard JSON itself doesn't need changes — it uses the `${DS_INFLUXDB}` variable which resolves from the provisioned datasource.

**Changes required**:
- Update `influxdb.yml` datasource: URL from `host.docker.internal:8086` to `influxdb:8086`
- Update `GF_SERVER_ROOT_URL` to reflect HOLYGRAIL IP or Traefik hostname
- Dashboard JSON: no changes needed (uses datasource variable)

## R-008: Portainer Integration with Traefik

**Decision**: Add Traefik network and labels to Portainer compose.

**Rationale**: Portainer is already deployed on HOLYGRAIL. To give it a clean URL (`portainer.holygrail`), it needs to join the shared `holygrail-proxy` network and have Traefik routing labels. Portainer currently uses HTTPS on port 9443 — Traefik can terminate HTTP and proxy to Portainer's HTTPS port, or route directly.

**Implementation**: Add `holygrail-proxy` external network and Traefik labels to the existing Portainer compose file. Since Portainer uses HTTPS (port 9443), configure Traefik to use the `https` transport scheme for this backend.
