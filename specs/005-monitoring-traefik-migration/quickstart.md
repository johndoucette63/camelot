# Quickstart: Monitoring Migration & Traefik Reverse Proxy

**Feature Branch**: `005-monitoring-traefik-migration`  
**Date**: 2026-04-08

## Prerequisites

- HOLYGRAIL running Ubuntu 24.04 LTS with Docker Engine + Docker Compose v2
- NVIDIA drivers and nvidia-container-toolkit installed (Phase 1 complete)
- SSH access to HOLYGRAIL: `ssh john@holygrail`
- Mac workstation on the same LAN (192.168.10.0/24)

## Deployment Order

### Step 1: Create Shared Docker Network

```bash
ssh john@holygrail "docker network create holygrail-proxy"
```

This external network is shared by all HOLYGRAIL compose stacks so Traefik can route to them.

### Step 2: Deploy Traefik

```bash
# Copy configs to HOLYGRAIL
scp -r infrastructure/holygrail/traefik/ john@holygrail:~/docker/traefik/

# Create .env from example
ssh john@holygrail "cp ~/docker/traefik/.env.example ~/docker/traefik/.env"
# Edit .env if needed

# Start Traefik
ssh john@holygrail "cd ~/docker/traefik && docker compose up -d"
```

Verify: `curl -s http://192.168.10.129:8080/api/overview` should return Traefik API data.

### Step 3: Deploy Monitoring Stack

```bash
# Copy monitoring compose and configs to HOLYGRAIL
scp -r infrastructure/holygrail/monitoring/ john@holygrail:~/docker/monitoring/
scp -r infrastructure/monitoring/smokeping/ john@holygrail:~/docker/monitoring/smokeping/
scp -r infrastructure/monitoring/grafana/ john@holygrail:~/docker/monitoring/grafana/
scp -r infrastructure/monitoring/scripts/ john@holygrail:~/docker/monitoring/scripts/

# Create .env from example
ssh john@holygrail "cp ~/docker/monitoring/.env.example ~/docker/monitoring/.env"
# Edit .env with actual credentials

# Start monitoring
ssh john@holygrail "cd ~/docker/monitoring && docker compose up -d"
```

Verify services:
- Grafana: `curl -s http://192.168.10.129:3000/api/health`
- Smokeping: `curl -s -o /dev/null -w '%{http_code}' http://192.168.10.129:8080`
- InfluxDB: `curl -s http://192.168.10.129:8086/ping`

### Step 4: Configure Mac DNS

Add to `/etc/hosts` on the Mac:

```
# HOLYGRAIL services (Camelot)
192.168.10.129  grafana.holygrail
192.168.10.129  smokeping.holygrail
192.168.10.129  plex.holygrail
192.168.10.129  portainer.holygrail
192.168.10.129  traefik.holygrail
```

```bash
sudo sh -c 'cat >> /etc/hosts << EOF

# HOLYGRAIL services (Camelot)
192.168.10.129  grafana.holygrail
192.168.10.129  smokeping.holygrail
192.168.10.129  plex.holygrail
192.168.10.129  portainer.holygrail
192.168.10.129  traefik.holygrail
EOF'
```

### Step 5: Verify Traefik Routes

After DNS is configured, test each hostname:

```bash
curl -s -o /dev/null -w '%{http_code}' http://grafana.holygrail
curl -s -o /dev/null -w '%{http_code}' http://smokeping.holygrail
curl -s -o /dev/null -w '%{http_code}' http://plex.holygrail/identity
curl -s -o /dev/null -w '%{http_code}' http://portainer.holygrail
curl -s -o /dev/null -w '%{http_code}' http://traefik.holygrail
```

All should return `200`.

### Step 6: Verify Monitoring Data Flow

1. Open `http://grafana.holygrail` → login with credentials from `.env`
2. Navigate to Network Monitoring dashboard
3. Confirm all panels show live data (allow 5-10 minutes for initial data collection)
4. Check Smokeping UI at `http://smokeping.holygrail` for active target monitoring

## Rollback

If issues arise, the Torrentbox monitoring stack is still running in parallel:
- Grafana: `http://192.168.10.141:3000`
- Smokeping: `http://192.168.10.141:8080`

To stop HOLYGRAIL monitoring without affecting other services:
```bash
ssh john@holygrail "cd ~/docker/monitoring && docker compose down"
```

## Files Modified (Repository)

| Path | Change |
|------|--------|
| `infrastructure/holygrail/monitoring/docker-compose.yml` | New — monitoring stack for HOLYGRAIL |
| `infrastructure/holygrail/traefik/docker-compose.yml` | New — Traefik reverse proxy |
| `infrastructure/holygrail/traefik/config/dynamic.yml` | New — file provider routes (Plex) |
| `infrastructure/monitoring/smokeping/Targets` | Updated — Plex→HOLYGRAIL target |
| `infrastructure/monitoring/grafana/provisioning/datasources/influxdb.yml` | Updated — Docker network URL |
| `infrastructure/holygrail/docker/portainer-compose.yml` | Updated — Traefik network + labels |
| `docs/INFRASTRUCTURE.md` | Updated — new service locations |
