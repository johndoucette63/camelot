# Quickstart: Device Enrichment & Auto-Identification

**Branch**: `013-device-enrichment` | **Date**: 2026-04-13

## Prerequisites

- Docker Compose running the advisor stack on HOLYGRAIL
- PostgreSQL 16 with existing advisor database (migrations 001-006 applied)
- nmap installed in the scanner container (already present in Dockerfile)

## Setup Steps

### 1. Apply database migration

```bash
# On HOLYGRAIL — run migration inside the backend container
ssh john@holygrail
cd ~/advisor
docker compose exec backend alembic upgrade head
```

Verify migration applied:
```bash
docker compose exec backend alembic current
# Should show: 007_device_enrichment (head)
```

### 2. Rebuild and restart the scanner

```bash
# On HOLYGRAIL
docker compose build scanner
docker compose up -d scanner
```

### 3. Rebuild and restart the frontend

```bash
# On HOLYGRAIL
docker compose build frontend
docker compose up -d frontend
```

### 4. Rebuild and restart the backend (API changes)

```bash
# On HOLYGRAIL
docker compose build backend
docker compose up -d backend
```

Or rebuild everything at once:
```bash
docker compose up -d --build
```

## Verification

### Check scanner logs for enrichment activity

```bash
ssh john@holygrail
docker compose logs -f scanner --tail=50
```

Expected log entries after a scan cycle:
```
{"level": "INFO", "logger": "scanner", "message": "Starting enrichment", ...}
{"level": "INFO", "logger": "scanner", "message": "mDNS cache: N devices discovered", ...}
{"level": "INFO", "logger": "scanner", "message": "Fingerprinting N devices", ...}
{"level": "INFO", "logger": "scanner", "message": "SSDP discovery: N devices found", ...}
{"level": "INFO", "logger": "scanner", "message": "Auto-classified N devices", ...}
{"level": "INFO", "logger": "scanner", "message": "Enrichment finished", ...}
```

### Verify enrichment data in the API

```bash
# From Mac workstation
curl -s http://advisor.holygrail/api/devices | python3 -m json.tool | head -40
```

Check that devices have new fields populated:
- `os_family` should show OS for fingerprinted devices
- `mdns_name` should show names for Apple/mDNS-advertising devices
- `annotation.classification_source` should show "mdns", "nmap", etc. for auto-classified devices

### Verify frontend displays enrichment data

1. Open `http://advisor.holygrail/devices` in a browser
2. Confirm the "OS" column appears in the device table
3. Confirm auto-classified roles show an "(auto)" indicator
4. Click a device row to open the detail modal
5. Confirm the "Identification" section shows enrichment metadata
6. Click "Re-scan" on a device and verify it gets re-enriched on the next cycle

### Test the re-enrich endpoint

```bash
# Replace with an actual MAC address from your network
curl -s -X POST http://advisor.holygrail/api/devices/AA:BB:CC:DD:EE:FF/re-enrich
# Expected: {"message": "Device queued for re-enrichment", "mac_address": "AA:BB:CC:DD:EE:FF"}
```

## Rollback

If something goes wrong:

```bash
# On HOLYGRAIL — rollback migration
docker compose exec backend alembic downgrade 006_device_monitor_offline

# Rebuild without enrichment code (checkout previous branch)
docker compose up -d --build
```

## Timing Notes

- The mDNS listener needs ~60 seconds of passive listening to build its cache before enrichment data is meaningful.
- The first enrichment cycle after restart may only fingerprint 5 devices (rate limit). Subsequent cycles will catch the rest.
- A full enrichment of all ~20 devices on the network will take 4-5 scan cycles (at 5 devices per cycle for active fingerprinting).
