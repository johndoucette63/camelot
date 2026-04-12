# API Contracts: Advisor Learnings & Curated Notes

**Branch**: `012-advisor-learnings-notes` | **Date**: 2026-04-12

All endpoints are prefixed with `/api`. Request/response bodies are JSON. Timestamps are ISO 8601 with timezone.

---

## Notes CRUD

### List Notes

```
GET /api/notes?target_type={type}&target_id={id}&tag={tag}
```

**Query Parameters:**

| Param | Type | Required | Description |
| --- | --- | --- | --- |
| `target_type` | string | Yes | One of: `device`, `service`, `playbook` |
| `target_id` | integer | No | Required for `device`/`service`. Omit for `playbook`. |
| `tag` | string | No | Filter playbook entries by tag (exact match). Only valid when `target_type=playbook`. |

**Response: 200 OK**

```json
{
  "notes": [
    {
      "id": 1,
      "target_type": "device",
      "target_id": 5,
      "title": null,
      "body": "Goes offline Sunday 2 AM for RAID scrub",
      "pinned": true,
      "tags": [],
      "created_at": "2026-04-12T10:00:00Z",
      "updated_at": "2026-04-12T10:00:00Z"
    }
  ],
  "total": 1
}
```

Notes are sorted by `updated_at DESC`.

---

### Create Note

```
POST /api/notes
```

**Request Body:**

```json
{
  "target_type": "device",
  "target_id": 5,
  "title": null,
  "body": "Goes offline Sunday 2 AM for RAID scrub",
  "pinned": false,
  "tags": []
}
```

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `target_type` | string | Yes | `device`, `service`, or `playbook` |
| `target_id` | integer | Conditional | Required for device/service. Must be null/omitted for playbook. |
| `title` | string | No | Max 200 chars. Typically provided for playbook entries. |
| `body` | string | Yes | Non-empty, max 2048 bytes. |
| `pinned` | boolean | No | Default: false |
| `tags` | string[] | No | Default: []. Free-form strings. |

**Response: 201 Created**

```json
{
  "id": 1,
  "target_type": "device",
  "target_id": 5,
  "title": null,
  "body": "Goes offline Sunday 2 AM for RAID scrub",
  "pinned": false,
  "tags": [],
  "created_at": "2026-04-12T10:00:00Z",
  "updated_at": "2026-04-12T10:00:00Z"
}
```

**Error Responses:**

| Status | Condition |
| --- | --- |
| 400 | Empty body, body exceeds 2048 bytes, invalid target_type |
| 404 | target_id references a non-existent device or service |
| 409 | Pinning would exceed 20-pinned-per-category limit |

---

### Update Note

```
PATCH /api/notes/{note_id}
```

**Request Body** (all fields optional, only provided fields are updated):

```json
{
  "title": "Updated title",
  "body": "Updated content",
  "pinned": true,
  "tags": ["maintenance", "vendor"]
}
```

**Response: 200 OK** — Returns the full updated note object.

**Error Responses:**

| Status | Condition |
| --- | --- |
| 400 | Empty body, body exceeds 2048 bytes |
| 404 | Note not found |
| 409 | Pinning would exceed 20-pinned-per-category limit |

---

### Delete Note

```
DELETE /api/notes/{note_id}
```

**Response: 204 No Content**

**Error Responses:**

| Status | Condition |
| --- | --- |
| 404 | Note not found |

---

### List Unique Tags (Autocomplete)

```
GET /api/notes/tags
```

Returns all distinct tags used across playbook entries, sorted alphabetically. Used by the frontend tag input for autocomplete.

**Response: 200 OK**

```json
{
  "tags": ["convention", "dns", "maintenance", "security", "vendor"]
}
```

---

## Note Suggestions

### Generate Suggestions

```
POST /api/chat/conversations/{conversation_id}/suggest-notes
```

Triggers an LLM call to extract 0–3 note suggestions from the conversation. Filters out previously rejected suggestions by content hash.

**Request Body:** None.

**Response: 200 OK**

```json
{
  "suggestions": [
    {
      "target_type": "device",
      "target_id": 3,
      "target_label": "NAS",
      "body": "The NAS scrub happens every Sunday at 2 AM"
    },
    {
      "target_type": "playbook",
      "target_id": null,
      "target_label": null,
      "body": "DNS provider was switched to Cloudflare last week"
    }
  ]
}
```

Each suggestion includes a `target_label` (human-readable device/service name) for display in the review panel.

**Error Responses:**

| Status | Condition |
| --- | --- |
| 404 | Conversation not found |
| 503 | LLM service unavailable (Ollama unreachable) — returns `{"suggestions": [], "error": "LLM service unavailable"}` with status 200, not 503, per FR-019 (graceful degradation) |

Note: LLM unavailability returns 200 with empty suggestions, not an error status, to avoid breaking the frontend flow.

---

### Reject Suggestion

```
POST /api/notes/rejected-suggestions
```

Records a rejected suggestion to prevent it from being suggested again.

**Request Body:**

```json
{
  "body": "The NAS scrub happens every Sunday at 2 AM",
  "conversation_id": 7
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string | Yes | The suggestion body text (will be hashed for dedup) |
| `conversation_id` | integer | No | Conversation where this was rejected |

**Response: 201 Created**

```json
{
  "id": 1,
  "content_hash": "a1b2c3...",
  "created_at": "2026-04-12T10:05:00Z"
}
```

**Response: 200 OK** — If this hash already exists (idempotent).

---

## Existing Endpoint Modifications

### Device Deletion Cascade

When a device is deleted (existing endpoint), all notes with `target_type='device'` and `target_id={device.id}` must be deleted in the same transaction.

### Service Definition Deletion Cascade

When a service definition is deleted (existing endpoint), all notes with `target_type='service'` and `target_id={service_definition.id}` must be deleted in the same transaction.
