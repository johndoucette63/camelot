# Quickstart: Network Discovery & Device Inventory

**Feature**: 008-network-discovery-inventory  
**Date**: 2026-04-09

---

## Prerequisites

- F4.1 advisor scaffold deployed and running on HOLYGRAIL (`docker compose up -d` in `advisor/`)
- HOLYGRAIL has internet access for initial `docker compose build` (to pull packages)
- Python 3.12+ locally for running migrations and tests

---

## Local Development

### 1. Install new backend dependencies

```bash
cd advisor/backend
pip install -r requirements.txt
# New packages: python-nmap, mac-vendor-lookup, alembic
```

### 2. Run database migration

```bash
cd advisor/backend
alembic upgrade head
# Applies: 001_network_discovery migration
```

### 3. Start the stack

```bash
cd advisor
docker compose up -d
```

The scanner sidecar will start automatically and run its first scan within the configured interval.

### 4. Verify the scanner is running

```bash
docker compose logs scanner -f
# Should show: "Starting scan of 192.168.10.0/24"
```

### 5. Check the API

```bash
# List discovered devices
curl http://localhost:8000/devices

# Check recent events
curl http://localhost:8000/events
```

### 6. Open the dashboard

Navigate to `http://advisor.holygrail` (or `http://localhost:5173` for dev mode).

---

## Production Deploy on HOLYGRAIL

```bash
# Pull latest code
cd ~/Code/camelot
git pull

# Rebuild and redeploy
cd advisor
docker compose build
docker compose up -d

# Run migration (once, against running postgres)
docker compose exec backend alembic upgrade head

# Verify
docker compose ps
docker compose logs scanner --tail=20
```

---

## Manual Scan Trigger

To trigger an immediate scan without waiting for the scheduled interval:

```bash
curl -X POST http://advisor.holygrail/api/scans/trigger
```

---

## Configuration

Scanner interval and other settings are configured via environment variables in `advisor/.env`:

```bash
SCAN_INTERVAL_SECONDS=900    # 15 minutes (default)
SCAN_TARGET=192.168.10.0/24  # target subnet
POSTGRES_PASSWORD=...         # required
```

---

## Running Tests

```bash
# Backend
cd advisor/backend
pytest tests/ -v

# Frontend
cd advisor/frontend
npm run test
```

---

## Troubleshooting

**Scanner container exits immediately**:
- Check logs: `docker compose logs scanner`
- Verify postgres is healthy: `docker compose ps postgres`
- Check `DATABASE_URL` in `.env` uses `127.0.0.1:5432` (not `postgres:5432`) for the scanner service

**No devices discovered / no MAC addresses**:
- Scanner must use `network_mode: host` to access ARP
- Verify scanner container config in `docker-compose.yml` has `network_mode: host`
- Verify postgres port is exposed to host: `ports: ["127.0.0.1:5432:5432"]`

**Migration fails ("column already exists")**:
- Alembic tracks applied migrations in `alembic_version` table
- Check current state: `docker compose exec backend alembic current`
- Do not re-run init.sql manually against an existing DB
