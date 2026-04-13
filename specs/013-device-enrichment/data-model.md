# Data Model: Device Enrichment & Auto-Identification

**Branch**: `013-device-enrichment` | **Date**: 2026-04-13

## Entity Changes

### Device (extended)

**Table**: `devices` (existing)

New columns added via migration `007_device_enrichment`:

| Column | Type | Default | Nullable | Description |
| --- | --- | --- | --- | --- |
| `os_family` | String(50) | NULL | Yes | Detected OS family: Linux, macOS, iOS, Windows, Android, etc. |
| `os_detail` | String(255) | NULL | Yes | Full OS string from fingerprinting (e.g., "Linux 5.15", "Apple iOS 17.4") |
| `mdns_name` | String(255) | NULL | Yes | Friendly name parsed from mDNS advertisement |
| `netbios_name` | String(255) | NULL | Yes | NetBIOS hostname discovered during fingerprinting |
| `ssdp_friendly_name` | String(255) | NULL | Yes | UPnP friendlyName from SSDP device description |
| `ssdp_model` | String(255) | NULL | Yes | UPnP modelName + modelNumber combined |
| `last_enriched_at` | DateTime | NULL | Yes | Timestamp of most recent enrichment pass |
| `enrichment_ip` | String(15) | NULL | Yes | IP at time of last enrichment (change triggers re-enrichment) |

### Annotation (extended)

**Table**: `annotations` (existing)

New columns added via migration `007_device_enrichment`:

| Column | Type | Default | Nullable | Description |
| --- | --- | --- | --- | --- |
| `classification_source` | String(50) | NULL | Yes | How role was assigned: "user", "mdns", "nmap", "ssdp", "vendor", or NULL |
| `classification_confidence` | String(10) | NULL | Yes | Confidence level: "high", "medium", "low", or NULL (for user-set) |

### Service (unchanged)

**Table**: `services` (existing, reused)

nmap-discovered open ports and services are upserted into this table using the existing `(device_id, name)` unique constraint. No schema changes needed.

## Relationships

```
Device (1) ──── (1) Annotation
  │                    ├── role (existing)
  │                    ├── classification_source (NEW)
  │                    └── classification_confidence (NEW)
  │
  ├── os_family (NEW)
  ├── os_detail (NEW)
  ├── mdns_name (NEW)
  ├── netbios_name (NEW)
  ├── ssdp_friendly_name (NEW)
  ├── ssdp_model (NEW)
  ├── last_enriched_at (NEW)
  └── enrichment_ip (NEW)
  │
  └── (1:many) Service
        ├── name
        ├── port
        └── status
```

## Display Name Resolution Chain

The frontend resolves the best available display name using this priority (highest first):

1. `annotation.description` — user-provided description (never overwritten)
2. `hostname` — DNS hostname from nmap reverse lookup (existing)
3. `mdns_name` — friendly name from mDNS advertisement
4. `netbios_name` — NetBIOS hostname
5. `ssdp_friendly_name` — UPnP friendly name
6. MAC address fallback

All source values are stored in their dedicated columns and preserved regardless of which is displayed.

## Enrichment State Machine

```
[Unenriched]                    [Enriched]
  Device has                      Device has
  last_enriched_at = NULL         last_enriched_at != NULL
  │                               │
  │── enrichment pass runs ──────>│
  │                               │
  │<── IP changed ────────────────│  (enrichment_ip != current ip_address)
  │<── manual re-scan ────────────│  (last_enriched_at cleared via API)
```

## Classification State

```
Annotation.role = "unknown"           # No classification yet
  │
  ├── auto_classify() runs ──> role = "printer", classification_source = "mdns",
  │                            classification_confidence = "high"
  │
  └── user sets role via API ──> role = "camera", classification_source = "user",
                                 classification_confidence = NULL
```

- Auto-classification only fires when `classification_source` is NOT "user"
- User-set roles are never overwritten by auto-classification
- When a user clears their role back to "unknown", `classification_source` resets to NULL, allowing auto-classification to run again

## Migration: 007_device_enrichment

**Revision**: `007_device_enrichment`
**Down-revision**: `006_device_monitor_offline`

**Upgrade operations**:
1. Add 8 columns to `devices`: os_family, os_detail, mdns_name, netbios_name, ssdp_friendly_name, ssdp_model, last_enriched_at, enrichment_ip
2. Add 2 columns to `annotations`: classification_source, classification_confidence
3. Set `classification_source = 'user'` for all existing annotations where `role != 'unknown'` (preserve existing manual classifications)

**Downgrade operations**:
1. Drop the 2 columns from `annotations`
2. Drop the 8 columns from `devices`
