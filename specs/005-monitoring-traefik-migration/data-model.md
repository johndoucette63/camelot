# Data Model: Monitoring Migration & Traefik Reverse Proxy

**Feature Branch**: `005-monitoring-traefik-migration`  
**Date**: 2026-04-08

## Overview

This feature is infrastructure-focused. There is no traditional application data model (no relational database, no ORM entities). The "data model" consists of time-series measurements in InfluxDB and configuration artifacts that define service routing and monitoring targets.

## InfluxDB Measurements

**Database**: `network_metrics`

### Measurement: `smokeping`

Stores latency and packet loss data collected by the Smokeping exporter.

| Field/Tag | Type | Description |
|-----------|------|-------------|
| `target` | tag | Hostname or IP of the monitored device (e.g., "Router", "NAS", "Google_DNS") |
| `latency_ms` | field (float) | Round-trip latency in milliseconds |
| `packet_loss` | field (float) | Packet loss percentage (0-100) |
| `time` | timestamp | Measurement timestamp (InfluxDB native) |

**Write frequency**: Every 5 minutes (Smokeping default probe interval)  
**Retention**: Default (infinite) — InfluxDB 1.8 default retention policy  
**Source**: Smokeping exporter parses RRD files and writes to InfluxDB

### Measurement: `speedtest`

Stores periodic bandwidth test results.

| Field/Tag | Type | Description |
|-----------|------|-------------|
| `download_mbps` | field (float) | Download speed in Mbps |
| `upload_mbps` | field (float) | Upload speed in Mbps |
| `ping_ms` | field (float) | Latency to speedtest server in ms |
| `server` | tag | Speedtest server used |
| `time` | timestamp | Measurement timestamp |

**Write frequency**: Every 30 minutes (SPEEDTEST_INTERVAL=1800)  
**Retention**: Default (infinite)  
**Source**: speedtest_logger.py runs speedtest-cli and writes results

## Configuration Entities

### Smokeping Targets

**File**: `infrastructure/monitoring/smokeping/Targets`  
**Format**: Smokeping hierarchical config (FPing probe)

| Section | Targets | Update Required |
|---------|---------|-----------------|
| Infrastructure | Router (.1), NAS (.105), HOLYGRAIL (.129), Torrentbox (.141) | Yes — rename Plex→HOLYGRAIL, update IP |
| Slow Devices | 9 devices with known high latency | Review for staleness |
| Network Ranges | .1-.50, .100-.125, .126-.150, .249-.250 | No change |
| External DNS | Cloudflare (1.1.1.1), Google (8.8.8.8) | No change |
| Internet Sites | google.com, cloudflare.com, amazon.com, netflix.com, github.com | No change |

### Traefik Routes

**Routing model**: Hostname-based (Host rule) → backend service

| Hostname | Backend | Network Mode | Discovery |
|----------|---------|-------------|-----------|
| `grafana.holygrail` | grafana:3000 | Bridge (holygrail-proxy) | Docker labels |
| `smokeping.holygrail` | smokeping:80 | Bridge (holygrail-proxy) | Docker labels |
| `portainer.holygrail` | portainer:9443 (HTTPS) | Bridge (holygrail-proxy) | Docker labels |
| `plex.holygrail` | 192.168.10.129:32400 | Host network | File provider (static) |
| `traefik.holygrail` | Traefik dashboard (internal) | N/A | Built-in API |

### Docker Networks

| Network | Type | Purpose |
|---------|------|---------|
| `holygrail-proxy` | External bridge | Shared network for Traefik ↔ backend communication |
| `monitoring` | Internal bridge | Internal monitoring stack communication (InfluxDB ↔ exporters) |

Services join both networks: `holygrail-proxy` for Traefik routing, `monitoring` for internal data flow (exporters → InfluxDB).

## State Transitions

### Migration State

```
Torrentbox Active → Parallel Running → HOLYGRAIL Active → Torrentbox Decommissioned
```

1. **Torrentbox Active**: Current state — all monitoring on Torrentbox
2. **Parallel Running**: Both stacks running for comparison/verification
3. **HOLYGRAIL Active**: HOLYGRAIL confirmed working, Torrentbox monitoring stopped
4. **Torrentbox Decommissioned**: Old monitoring configs archived in repo

### Service Health States (per Traefik)

```
Healthy → Unhealthy → Recovered
```

Traefik monitors backend health via Docker healthchecks. Unhealthy backends are removed from routing until recovery.
