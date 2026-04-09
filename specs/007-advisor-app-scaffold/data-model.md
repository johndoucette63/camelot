# Data Model: Network Advisor Application Scaffold

**Feature**: 007-advisor-app-scaffold
**Date**: 2026-04-08

## Entities

### Device

Represents a network device in the Camelot infrastructure.

| Field | Type | Constraints | Description |
| ----- | ---- | ----------- | ----------- |
| id | Integer | Primary key, auto-increment | Unique device identifier |
| hostname | String(100) | Not null, unique | Device hostname (e.g., "HOLYGRAIL") |
| ip_address | String(15) | Not null, unique | IPv4 address (e.g., "192.168.10.129") |
| device_type | String(50) | Not null | Category (e.g., "server", "raspberry_pi", "workstation") |
| status | String(20) | Not null, default "unknown" | Current status ("online", "offline", "unknown") |
| created_at | Timestamp | Not null, default now | Record creation time |
| updated_at | Timestamp | Not null, default now, update on modify | Last modification time |

**Uniqueness**: hostname and ip_address are each independently unique.

### Service

Represents a running service on a device.

| Field | Type | Constraints | Description |
| ----- | ---- | ----------- | ----------- |
| id | Integer | Primary key, auto-increment | Unique service identifier |
| device_id | Integer | Foreign key → Device.id, not null | Parent device |
| name | String(100) | Not null | Service name (e.g., "Plex", "Ollama", "Deluge") |
| port | Integer | Nullable | Network port (null if not applicable) |
| status | String(20) | Not null, default "unknown" | Current status ("running", "stopped", "unknown") |
| created_at | Timestamp | Not null, default now | Record creation time |
| updated_at | Timestamp | Not null, default now, update on modify | Last modification time |

**Relationships**: Many-to-one with Device. A device can have many services. Deleting a device cascades to its services.

**Uniqueness**: (device_id, name) is unique — no duplicate service names per device.

### Alert

Represents a monitoring event or notification.

| Field | Type | Constraints | Description |
| ----- | ---- | ----------- | ----------- |
| id | Integer | Primary key, auto-increment | Unique alert identifier |
| device_id | Integer | Foreign key → Device.id, nullable | Associated device (null for system-wide alerts) |
| service_id | Integer | Foreign key → Service.id, nullable | Associated service (null for device-level alerts) |
| severity | String(20) | Not null | Alert level: "info", "warning", "critical" |
| message | Text | Not null | Human-readable alert description |
| acknowledged | Boolean | Not null, default false | Whether the alert has been acknowledged |
| created_at | Timestamp | Not null, default now | When the alert was raised |

**Relationships**: Optional many-to-one with Device and Service. Alerts can exist at device level, service level, or system-wide (both null).

## Seed Data

The initial schema includes the 5 known Camelot network devices:

| hostname | ip_address | device_type | status |
| -------- | ---------- | ----------- | ------ |
| HOLYGRAIL | 192.168.10.129 | server | unknown |
| Torrentbox | 192.168.10.141 | raspberry_pi | unknown |
| NAS | 192.168.10.105 | raspberry_pi | unknown |
| Pi-hole DNS | 192.168.10.150 | raspberry_pi | unknown |
| Mac Workstation | 192.168.10.145 | workstation | unknown |

All devices start with `status = "unknown"`. Actual status discovery is deferred to F4.2+.

## Entity Relationship Diagram

```text
+----------+       +----------+       +---------+
|  Device  |1----*|  Service  |       |  Alert  |
+----------+       +----------+       +---------+
| id (PK)  |       | id (PK)  |       | id (PK) |
| hostname |       | device_id|---+   | device_id|---> Device (optional)
| ip_address|      | name     |   |   | service_id|--> Service (optional)
| device_type|     | port     |   |   | severity |
| status   |       | status   |   |   | message  |
| created_at|      | created_at|  |   | acknowledged|
| updated_at|      | updated_at|  |   | created_at|
+----------+       +----------+   |   +---------+
                                   |
                        cascade delete
```
