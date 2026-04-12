# Data Model: Advisor Learnings & Curated Notes

**Branch**: `012-advisor-learnings-notes` | **Date**: 2026-04-12

## Entity Relationship Overview

```
devices (existing)          service_definitions (existing)       conversations (existing)
   │                              │                                    │
   │ 1:many (app-level)           │ 1:many (app-level)                │ 1:many (app-level)
   ▼                              ▼                                    ▼
┌──────────────────────────────────────────┐           ┌──────────────────────────┐
│              notes                       │           │   rejected_suggestions   │
│──────────────────────────────────────────│           │──────────────────────────│
│ id               PK                      │           │ id              PK       │
│ target_type      'device'|'service'|     │           │ content_hash    UNIQUE   │
│                  'playbook'              │           │ conversation_id FK (SET  │
│ target_id        nullable int            │           │                 NULL)    │
│ title            nullable (playbook)     │           │ created_at               │
│ body             text, ≤2KB              │           └──────────────────────────┘
│ pinned           boolean                 │
│ tags             JSON array (playbook)   │
│ created_at                               │
│ updated_at                               │
└──────────────────────────────────────────┘
```

## Entities

### notes

The central table for all user-curated notes. Uses a polymorphic pattern (matching the existing `alerts.target_type`/`target_id` convention) to support three note categories in a single table.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | Integer | PK, auto-increment | Unique note identifier |
| `target_type` | String(20) | NOT NULL, CHECK IN ('device', 'service', 'playbook') | Category of note |
| `target_id` | Integer | Nullable | References `devices.id` (when target_type='device') or `service_definitions.id` (when target_type='service'). NULL for playbook entries. |
| `title` | String(200) | Nullable | Title for playbook entries. NULL for device/service notes. |
| `body` | Text | NOT NULL | Markdown content, max 2048 bytes. Validated at API level. |
| `pinned` | Boolean | NOT NULL, default=False | Pinned notes always appear in advisor grounding context. |
| `tags` | JSON | NOT NULL, default=[] | Tag array for playbook entries. Empty array for device/service notes. |
| `created_at` | DateTime(tz) | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime(tz) | NOT NULL, server_default=now(), onupdate=now() | Last modification timestamp |

**Indexes:**

| Name | Columns | Type | Purpose |
| --- | --- | --- | --- |
| `idx_notes_target` | (target_type, target_id) | B-tree | Fast lookup of notes for a specific device/service |
| `idx_notes_pinned` | (pinned, target_type) | B-tree | Efficient query for pinned notes by category (prompt assembler) |
| `idx_notes_updated_at` | (updated_at DESC) | B-tree | Sort by most recent |

**Validation rules:**
- `body` must not be empty and must not exceed 2048 bytes
- When `target_type = 'playbook'`: `target_id` MUST be NULL, `title` SHOULD be provided
- When `target_type = 'device'`: `target_id` MUST reference an existing `devices.id`
- When `target_type = 'service'`: `target_id` MUST reference an existing `service_definitions.id`
- Maximum 20 pinned notes per (`target_type`, `target_id`) combination, enforced at API level

**Cascade behavior:**
- No database-level FK (polymorphic pattern — matches alerts)
- Application-level cascade: when a device or service_definition is deleted, all notes with matching `target_type` and `target_id` are deleted in the same transaction

### rejected_suggestions

Tracks rejected note suggestions by content hash to prevent re-surfacing the same suggestion across conversations.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | Integer | PK, auto-increment | Unique identifier |
| `content_hash` | String(64) | NOT NULL, UNIQUE | SHA-256 hex digest of normalised suggestion body |
| `conversation_id` | Integer | Nullable, FK→conversations.id, ondelete=SET NULL | Conversation where the suggestion was rejected. SET NULL if conversation is deleted. |
| `created_at` | DateTime(tz) | NOT NULL, server_default=now() | Rejection timestamp |

**Indexes:**

| Name | Columns | Type | Purpose |
| --- | --- | --- | --- |
| `uq_rejected_suggestions_hash` | (content_hash) | UNIQUE | Fast dedup lookup and uniqueness enforcement |

**Normalisation for hashing:** lowercase the body, collapse all whitespace to single spaces, strip leading/trailing whitespace, then SHA-256 hex digest.

## Seed Data

Three playbook entries seeded on initial migration (FR-027):

| title | body | tags | pinned |
| --- | --- | --- | --- |
| NAS RAID Scrub Schedule | The NAS (192.168.10.105) runs a scheduled RAID scrub every Sunday 2:00 AM–3:00 AM. During this window the NAS may be unresponsive — this is expected, not an outage. | ["maintenance", "nas"] | true |
| VPN Credential Rotation | VPN credentials on the Torrentbox rotate on the first Monday of every month. Check 1Password for current credentials after rotation. | ["maintenance", "security", "vpn"] | false |
| DNS Ownership | Pi-hole DNS runs on 192.168.10.150. Upstream DNS is configured in the Pi-hole admin panel. Changes to DNS settings should be tested during the maintenance window. | ["dns", "convention"] | false |

## Migration

**Migration file**: `005_advisor_notes.py` (next sequential number after 004_recommendations_alerts)

**Upgrade steps:**
1. Create `notes` table with all columns, indexes, and CHECK constraint
2. Create `rejected_suggestions` table with unique index on content_hash
3. Insert 3 seed playbook entries

**Downgrade steps:**
1. Drop `rejected_suggestions` table
2. Drop `notes` table
