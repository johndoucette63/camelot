# API Contracts: Device Enrichment & Auto-Identification

**Branch**: `013-device-enrichment` | **Date**: 2026-04-13

## Modified Endpoints

### GET /devices

**Changes**: Response model `DeviceOut` gains enrichment fields.

**Response** `200 OK` — `list[DeviceOut]`:

```json
[
  {
    "id": 1,
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "ip_address": "192.168.10.141",
    "hostname": "torrentbox",
    "vendor": "Raspberry Pi Foundation",
    "first_seen": "2026-04-09T12:00:00Z",
    "last_seen": "2026-04-13T10:30:00Z",
    "is_online": true,
    "is_known_device": true,
    "monitor_offline": true,
    "os_family": "Linux",
    "os_detail": "Linux 6.1 (Debian)",
    "mdns_name": null,
    "netbios_name": null,
    "ssdp_friendly_name": null,
    "ssdp_model": null,
    "last_enriched_at": "2026-04-13T10:31:00Z",
    "annotation": {
      "role": "server",
      "description": "Torrent download box",
      "tags": ["pi", "downloads"],
      "classification_source": "user",
      "classification_confidence": null
    }
  }
]
```

**New fields on DeviceOut**:

| Field | Type | Description |
| --- | --- | --- |
| `os_family` | `string \| null` | Detected OS family |
| `os_detail` | `string \| null` | Full OS fingerprint string |
| `mdns_name` | `string \| null` | Parsed mDNS friendly name |
| `netbios_name` | `string \| null` | NetBIOS hostname |
| `ssdp_friendly_name` | `string \| null` | UPnP friendly name |
| `ssdp_model` | `string \| null` | UPnP model name + number |
| `last_enriched_at` | `string \| null` | ISO 8601 timestamp of last enrichment |

**New fields on AnnotationOut**:

| Field | Type | Description |
| --- | --- | --- |
| `classification_source` | `string \| null` | Who set the role: "user", "mdns", "nmap", "ssdp", "vendor" |
| `classification_confidence` | `string \| null` | Confidence: "high", "medium", "low" |

### GET /devices/{mac_address}

Same response schema changes as `GET /devices` (single `DeviceOut`).

### PATCH /devices/{mac_address}/annotation

**Changes**: When a user sets a role via this endpoint, the system MUST also set `classification_source = "user"` and `classification_confidence = NULL`. This prevents auto-classification from overwriting the user's choice.

Request and response schemas are otherwise unchanged.

## New Endpoints

### POST /devices/{mac_address}/re-enrich

Marks a device for re-enrichment on the next scan cycle by clearing its `last_enriched_at` timestamp.

**Request**: No body required.

**Response** `202 Accepted`:

```json
{
  "message": "Device queued for re-enrichment",
  "mac_address": "AA:BB:CC:DD:EE:FF"
}
```

**Error responses**:

| Status | Condition |
| --- | --- |
| 404 | Device with given MAC address not found |

**Behavior**:
- Sets `device.last_enriched_at = NULL`
- The next enrichment cycle will pick up this device as unenriched
- Idempotent — calling multiple times has no additional effect
