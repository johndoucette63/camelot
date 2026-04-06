# Network Latency Monitor

A comprehensive network monitoring stack for diagnosing intermittent slowdowns on your home network. Deployed on the Torrentbox Raspberry Pi 5.

## Components

| Service | Port | Description |
|---------|------|-------------|
| **Grafana** | 3000 | Unified dashboard for all metrics |
| **Smokeping** | 8080 | Continuous latency & packet loss monitoring |
| **InfluxDB** | 8086 | Time-series database for metric storage |
| **Speedtest** | - | Automated bandwidth testing every 30 min |

## Quick Access URLs

| Service | URL |
|---------|-----|
| Grafana Dashboard | http://192.168.10.141:3000 |
| Smokeping Native UI | http://192.168.10.141:8080 |
| InfluxDB API | http://192.168.10.141:8086 |

## Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| Grafana | admin | networkmon |
| InfluxDB | admin | influxadmin |
| InfluxDB (Grafana user) | grafana | grafanapass |

**Important:** Change these passwords after initial setup in a production environment.

## Installation

### 1. Copy files to Torrentbox

```bash
# From your workstation
scp -r monitoring/ john@192.168.10.141:~/docker/

# Or if you have the repo cloned
rsync -avz monitoring/ john@192.168.10.141:~/docker/monitoring/
```

### 2. SSH into Torrentbox

```bash
ssh john@192.168.10.141
```

### 3. Verify/Update Router IP

Check your actual gateway IP:
```bash
ip route | grep default
```

Edit the Smokeping Targets file if needed:
```bash
nano ~/docker/monitoring/smokeping/Targets
# Update the Router host IP on line ~11 if different from 192.168.10.1
```

### 4. Deploy the Stack

```bash
cd ~/docker/monitoring
docker compose up -d
```

### 5. Wait for Initial Data

- **Smokeping**: Data appears within 5 minutes
- **Speedtest**: First test runs ~30 seconds after startup, then every 30 minutes
- **Grafana**: Dashboard will populate as data arrives

## Using the Dashboard

### Access Grafana
1. Open http://192.168.10.141:3000
2. Login with `admin` / `networkmon`
3. The "Network Latency Monitor" dashboard loads automatically

### Dashboard Sections

**Overview Row:**
- Current latency stats for key targets
- Last speedtest download/upload speeds
- Average packet loss

**Latency Monitoring:**
- Local Network (Router, NAS, Plex)
- DNS Servers (Cloudflare, Google)
- Internet Sites (Google, Amazon, Netflix, etc.)

**Packet Loss:**
- Bar chart showing packet loss by target over time
- Threshold lines at 1% (yellow) and 5% (red)

**Bandwidth:**
- Download/Upload speed trends
- Ping and jitter from speedtests
- Table of recent speedtest results

### Time Range Selection

Use the time picker in the top-right to view:
- Last 1 hour (quick diagnosis)
- Last 24 hours (daily pattern)
- Last 7 days (weekly trends)
- Last 30 days (long-term analysis)

## Smokeping Native UI

For detailed historical graphs and raw data:
1. Open http://192.168.10.141:8080
2. Navigate the target hierarchy
3. View multi-scale graphs (hourly to yearly)

## Manual Operations

### Run Speedtest Immediately

```bash
cd ~/docker/monitoring
./scripts/run-speedtest.sh

# Or directly via docker:
docker exec speedtest python -c "from speedtest_logger import run_speedtest; print(run_speedtest())"
```

### Check Container Status

```bash
docker compose ps
docker compose logs -f smokeping
docker compose logs -f speedtest
```

### Restart Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart smokeping
docker compose restart grafana
```

### View Recent Logs

```bash
# Speedtest logs (see test results)
docker logs --tail 50 speedtest

# Smokeping exporter logs
docker logs --tail 50 smokeping-exporter

# Grafana logs
docker logs --tail 50 grafana
```

## Adding New Probe Targets

### 1. Edit Targets File

```bash
nano ~/docker/monitoring/smokeping/Targets
```

### 2. Add New Target

```
+ NewCategory
menu = New Category
title = New Category Title

++ NewTarget
menu = Target Name
title = Full Target Description
host = hostname.or.ip.address
```

### 3. Restart Smokeping

```bash
docker compose restart smokeping
```

The new target will appear in both Smokeping UI and Grafana within minutes.

## Persistent Data Locations

| Data | Docker Volume | Purpose |
|------|---------------|---------|
| InfluxDB | influxdb_data | All time-series metrics |
| Grafana | grafana_data | Dashboard configs, users |
| Smokeping Data | smokeping_data | RRD files with historical data |
| Smokeping Config | smokeping_config | Generated configuration |

### Backup Volumes

```bash
# List volumes
docker volume ls | grep monitoring

# Backup InfluxDB data
docker run --rm -v monitoring_influxdb_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/influxdb-backup.tar.gz /data

# Backup Grafana data
docker run --rm -v monitoring_grafana_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/grafana-backup.tar.gz /data
```

## Data Retention

- **InfluxDB**: Retains all data (configure retention policy for long-term)
- **Smokeping RRD**: ~2 years of historical data at decreasing resolution
- **Speedtest**: Runs every 30 minutes = 48 tests/day = ~1,440/month

To set InfluxDB retention (keep 90 days):
```bash
docker exec influxdb influx -username admin -password influxadmin \
  -execute "CREATE RETENTION POLICY ninety_days ON network_metrics DURATION 90d REPLICATION 1 DEFAULT"
```

## Troubleshooting

### No Data in Grafana

1. Check InfluxDB is receiving data:
   ```bash
   docker exec influxdb influx -username admin -password influxadmin \
     -database network_metrics -execute "SELECT * FROM smokeping LIMIT 5"
   ```

2. Check Smokeping is running:
   ```bash
   docker logs smokeping
   ```

3. Check exporter is connected:
   ```bash
   docker logs smokeping-exporter
   ```

### Speedtest Failing

1. Check if VPN is blocking speedtest:
   ```bash
   docker exec speedtest curl -s ifconfig.me
   ```
   If blocked, speedtest may need to bypass VPN.

2. Check speedtest logs:
   ```bash
   docker logs speedtest
   ```

### High Memory Usage

InfluxDB 1.8 is lighter than Prometheus but still uses memory. If the Pi is struggling:

1. Reduce speedtest frequency in docker-compose.yml:
   ```yaml
   SPEEDTEST_INTERVAL=3600  # Every hour instead of 30 min
   ```

2. Reduce Smokeping probe frequency (edit Targets, add `step = 600` for 10-min intervals)

### Port Conflicts

If ports are already in use, edit docker-compose.yml:
```yaml
ports:
  - "3001:3000"  # Change Grafana to 3001
  - "8081:80"    # Change Smokeping to 8081
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Network Latency Monitor                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ┌─────────────┐     ┌─────────────────┐     ┌─────────────┐   │
│   │  Smokeping  │────▶│ Smokeping       │────▶│             │   │
│   │  (probes)   │     │ Exporter        │     │             │   │
│   │  port 8080  │     │ (RRD parser)    │     │  InfluxDB   │   │
│   └─────────────┘     └─────────────────┘     │  port 8086  │   │
│                                               │             │   │
│   ┌─────────────┐                             │             │   │
│   │  Speedtest  │────────────────────────────▶│             │   │
│   │  (30 min)   │                             │             │   │
│   └─────────────┘                             └──────┬──────┘   │
│                                                      │          │
│                                                      ▼          │
│                                               ┌─────────────┐   │
│                                               │   Grafana   │   │
│                                               │  port 3000  │   │
│                                               └─────────────┘   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Probe Targets:
├── Local Network
│   ├── Router (192.168.10.1)
│   ├── NAS (192.168.10.105)
│   └── Plex (192.168.10.150)
├── DNS Servers
│   ├── Cloudflare (1.1.1.1)
│   ├── Google (8.8.8.8)
│   └── Google Secondary (8.8.4.4)
└── Internet Sites
    ├── google.com
    ├── cloudflare.com
    ├── amazon.com
    ├── netflix.com
    └── github.com
```

## Interpreting Results

### Latency Patterns

| Pattern | Likely Cause |
|---------|--------------|
| Router latency spikes | Local network congestion, router issue |
| All targets spike together | ISP issue or modem problem |
| Only internet sites spike | ISP routing issue |
| DNS high, others normal | DNS server issue |
| Gradual increase over time | Memory leak, needs reboot |

### When to Power Cycle

If you see:
- Router latency > 50ms sustained
- Packet loss > 5% on router
- All external targets unreachable but router responds

This indicates the router/modem needs attention.

### Healthy Baselines

| Metric | Good | Warning | Problem |
|--------|------|---------|---------|
| Router latency | < 5ms | 5-20ms | > 50ms |
| DNS latency | < 30ms | 30-50ms | > 100ms |
| Internet latency | < 50ms | 50-100ms | > 200ms |
| Packet loss | 0% | < 1% | > 5% |
| Download speed | > 80% of plan | 50-80% | < 50% |

---

*Deployed on Torrentbox (192.168.10.141) - Raspberry Pi 5 (8GB)*
