# Data Model: Network Discovery & Device Inventory

**Feature**: 008-network-discovery-inventory  
**Date**: 2026-04-09

---

## Overview

This feature extends the F4.1 schema with four changes:
1. **`devices` table** — heavily extended (add MAC, vendor, timestamps, online tracking)
2. **`annotations` table** — new, one-to-one with device
3. **`scans` table** — new, records each scan pass
4. **`events` table** — new, records notable network changes

The `services` and `alerts` tables from F4.1 are **unchanged** (FK to `devices.id` remains valid).

---

## Table: `devices` (modified)

Canonical identity key is `mac_address`. The existing `id` (SERIAL) is kept for FK references from `services`, `alerts`, and new tables.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | SERIAL | PRIMARY KEY | Preserved from F4.1 |
| `mac_address` | VARCHAR(17) | UNIQUE NOT NULL | Canonical identity — format: `AA:BB:CC:DD:EE:FF` |
| `ip_address` | VARCHAR(15) | NOT NULL | Most-recently observed; may change across scans |
| `hostname` | VARCHAR(255) | NULLABLE | Resolved via reverse DNS; null if unresolvable |
| `vendor` | VARCHAR(255) | NULLABLE | Derived from MAC OUI prefix at discovery time |
| `first_seen` | TIMESTAMP | NOT NULL | Timestamp of first discovery |
| `last_seen` | TIMESTAMP | NOT NULL | Timestamp of last successful scan response |
| `is_online` | BOOLEAN | NOT NULL DEFAULT FALSE | True if responded in most recent successful scan |
| `consecutive_missed_scans` | INTEGER | NOT NULL DEFAULT 0 | Reset to 0 on response; incremented on miss |
| `is_known_device` | BOOLEAN | NOT NULL DEFAULT FALSE | True for the 5 pre-seeded Camelot devices |

**Removed from F4.1**: `hostname UNIQUE` constraint (hostname may change or be null), `device_type` column (moved to `annotations.role`), `status` column (replaced by `is_online`).

**Migration note**: The F4.1 `hostname UNIQUE` and `ip_address UNIQUE` constraints must be dropped. A new `mac_address` UNIQUE constraint is added. The `device_type` and `status` columns are dropped after data is migrated to annotations.

**Indexes**:
- `idx_devices_mac` UNIQUE on `mac_address`
- `idx_devices_ip` on `ip_address` (non-unique; for lookup by IP)
- `idx_devices_is_online` on `is_online` (filter online/offline quickly)

---

## Table: `annotations` (new)

One-to-one with `devices`. Stores human-assigned metadata.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | SERIAL | PRIMARY KEY | |
| `device_id` | INTEGER | NOT NULL, UNIQUE, FK → devices(id) ON DELETE CASCADE | |
| `role` | VARCHAR(50) | NOT NULL DEFAULT 'unknown' | Enum: server, workstation, iot, storage, networking, printer, dns, unknown |
| `description` | TEXT | NULLABLE | Free-text description |
| `tags` | TEXT[] | NOT NULL DEFAULT '{}' | Array of tag strings |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**Constraint**: UNIQUE on `device_id` (enforces one-to-one).

**Pre-populated annotations** (inserted alongside F4.1 seed devices in migration):

| Device | Role | Description |
|--------|------|-------------|
| HOLYGRAIL | server | Ryzen 7800X3D — central server (Plex, Ollama, monitoring, advisor) |
| Torrentbox | server | Raspberry Pi 5 — Deluge + *arr apps + VPN |
| NAS | storage | Raspberry Pi 4 — OpenMediaVault, SMB shares |
| Pi-hole DNS | dns | Raspberry Pi 5 — Pi-hole DNS server |
| Mac Workstation | workstation | MacBook Pro M4 Pro — dev/management workstation |

---

## Table: `scans` (new)

One record per scan pass.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | SERIAL | PRIMARY KEY | |
| `started_at` | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| `completed_at` | TIMESTAMP | NULLABLE | Null if scan failed or still running |
| `status` | VARCHAR(20) | NOT NULL DEFAULT 'running' | Values: `running`, `completed`, `failed` |
| `devices_found` | INTEGER | NULLABLE | Count of responding hosts in this scan |
| `new_devices` | INTEGER | NULLABLE DEFAULT 0 | Count of first-time devices discovered |
| `error_detail` | TEXT | NULLABLE | Error message if status = `failed` |

**Index**: `idx_scans_started_at` on `started_at DESC` (recent scans lookup).

---

## Table: `events` (new)

Records notable network changes. Retained for 30 days; older rows purged automatically.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | SERIAL | PRIMARY KEY | |
| `event_type` | VARCHAR(20) | NOT NULL | Values: `new-device`, `offline`, `back-online`, `scan-error` |
| `device_id` | INTEGER | NULLABLE, FK → devices(id) ON DELETE SET NULL | Null for `scan-error` events |
| `scan_id` | INTEGER | NULLABLE, FK → scans(id) ON DELETE SET NULL | Scan that generated the event |
| `timestamp` | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| `details` | JSONB | NULLABLE | Extra context (e.g., previous IP, error message) |

**Indexes**:
- `idx_events_timestamp` on `timestamp DESC` (recent events, 30-day purge query)
- `idx_events_event_type` on `event_type` (filter by type)
- `idx_events_device_id` on `device_id` (events per device)

**Retention**: A background task in the scanner purges `events` rows where `timestamp < NOW() - INTERVAL '30 days'` at the start of each scan cycle.

---

## Entity Relationships

```
devices (1) ──── (0..1) annotations
devices (1) ──── (0..*) services     [F4.1 unchanged]
devices (1) ──── (0..*) alerts       [F4.1 unchanged]
devices (1) ──── (0..*) events       [via device_id, nullable]
scans   (1) ──── (0..*) events       [via scan_id, nullable]
```

---

## State Transitions: Device Online Status

```
[first seen] → is_online=TRUE, consecutive_missed_scans=0
     ↓
[scan: responds] → is_online=TRUE, consecutive_missed_scans=0  (no event)
     ↓
[scan: no response] → consecutive_missed_scans += 1
     ↓ (if consecutive_missed_scans >= 2)
     → is_online=FALSE  [EVENT: offline]
     ↓
[scan: responds again] → is_online=TRUE, consecutive_missed_scans=0  [EVENT: back-online]
```

**Scan failure** (scan-error): consecutive_missed_scans is NOT incremented; is_online is NOT changed. A `scan-error` event is logged.

---

## Migration Plan

**Alembic revision**: `001_network_discovery`

Steps (in order, reversible):
1. Add columns to `devices`: `mac_address`, `vendor`, `first_seen`, `last_seen`, `is_online`, `consecutive_missed_scans`, `is_known_device`
2. Populate `mac_address` for existing 5 seed devices (known MACs from CLAUDE.md cannot be assumed — populate as 'UNKNOWN:00', 'UNKNOWN:01', etc. as placeholders; real MACs assigned on first scan)
3. Drop UNIQUE constraint on `hostname` and `ip_address` in `devices`
4. Add UNIQUE constraint on `mac_address`
5. Drop columns `device_type`, `status` from `devices` (after data noted)
6. Create `annotations` table; insert 5 pre-populated rows for seed devices
7. Create `scans` table
8. Create `events` table
9. Create all indexes
