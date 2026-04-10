# Chat API Contract

**Feature**: 010-ai-advisor-chat
**Base URL**: `http://advisor.holygrail` (production), `http://localhost:8000` (local dev)
**Router prefix**: `/chat`
**Auth**: None (single-admin LAN deployment — inherits the existing advisor app's posture; adding auth is out of scope for v1)

All endpoints return `application/json` except `POST /chat/conversations/{id}/messages`, which streams `application/x-ndjson`.

---

## `GET /chat/conversations/latest`

Fetch the most recently updated conversation. Used on page load so a quick reload preserves context (FR-006a).

### Response `200 OK`

```json
{
  "id": "b3a1c8d2-4f7e-4d2f-9a1e-cccccccccccc",
  "created_at": "2026-04-10T14:02:11.123Z",
  "updated_at": "2026-04-10T14:05:44.987Z",
  "title": null,
  "messages": [
    {
      "id": "ae55f2a0-1111-4444-9999-222222222222",
      "role": "user",
      "content": "What devices are on my network?",
      "created_at": "2026-04-10T14:02:11.456Z",
      "finished_at": null,
      "cancelled": false
    },
    {
      "id": "ae55f2a0-3333-4444-9999-222222222222",
      "role": "assistant",
      "content": "You have 5 devices: HOLYGRAIL, Torrentbox...",
      "created_at": "2026-04-10T14:02:11.789Z",
      "finished_at": "2026-04-10T14:02:14.123Z",
      "cancelled": false
    }
  ]
}
```

Messages are returned in chronological order (`created_at` ascending).

### Response `204 No Content`

Returned when there are no conversations in the database yet. The frontend MUST handle this by rendering an empty chat panel.

### Errors

- `503 Service Unavailable` — database unreachable.

---

## `POST /chat/conversations`

Create a new, empty conversation. Invoked by the "New chat" control (FR-006b). The new conversation becomes the active one on the frontend.

### Request body

Empty.

### Response `201 Created`

```json
{
  "id": "e7b2f4c6-8888-4444-aaaa-111111111111",
  "created_at": "2026-04-10T14:10:00.000Z",
  "updated_at": "2026-04-10T14:10:00.000Z",
  "title": null,
  "messages": []
}
```

### Errors

- `503 Service Unavailable` — database unreachable.

---

## `GET /chat/conversations/{conversation_id}`

Fetch a specific conversation and its message history. Used on hard refresh when the frontend knows the active conversation id (e.g., from URL or local state), and for test fixtures.

### Path parameters

| Name | Type | Description |
| --- | --- | --- |
| `conversation_id` | UUID | ID of the conversation to fetch. |

### Response `200 OK`

Same shape as `GET /chat/conversations/latest` (200 response).

### Errors

- `404 Not Found` — no conversation with that id.
- `503 Service Unavailable` — database unreachable.

---

## `POST /chat/conversations/{conversation_id}/messages`

Submit a user message to a conversation and stream the advisor's reply back as newline-delimited JSON frames. This is the main interactive endpoint.

### Path parameters

| Name | Type | Description |
| --- | --- | --- |
| `conversation_id` | UUID | ID of the conversation to post to. Must exist. |

### Request body

```json
{
  "content": "Which services are down right now?"
}
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `content` | string | yes | Non-empty, non-whitespace. Trimmed server-side. Max length: 8 KB (enforced at the request schema; user questions never approach this). |

### Response `200 OK` (streaming)

Content-Type: `application/x-ndjson`

Each line in the body is one JSON object ("frame"). Frames arrive progressively as the Ollama model generates tokens. The client reads them with `fetch().body.getReader()` (see `services/chat.ts` in the plan).

Frame envelope:

```jsonc
// Frame 0: stream start — emitted exactly once at the top, carries the
// persistent assistant message id so the client can correlate later frames.
{"type": "start", "message_id": "ae55f2a0-3333-4444-9999-222222222222"}

// Frames 1..N-1: tokens — emitted as the model generates content.
// Content may be a single token or a small batch (Ollama sometimes coalesces).
{"type": "token", "content": "You "}
{"type": "token", "content": "have "}
{"type": "token", "content": "5 devices..."}

// Final frame on success: done — emitted exactly once.
{"type": "done", "message_id": "...", "duration_ms": 2341, "cancelled": false}

// OR: error — emitted exactly once if something went wrong before completion.
// Replaces the done frame. Client MUST treat as a terminal state.
{"type": "error", "message_id": "...", "message": "The advisor is temporarily unavailable. Please try again."}
```

Exact frame ordering guarantees:

1. Exactly one `start` frame, first.
2. Zero or more `token` frames, in order.
3. Exactly one terminal frame (`done` OR `error`), last.
4. If the client disconnects (stop button / page close / network drop), the backend stops emitting frames, persists whatever was in the token buffer as the assistant message's `content`, and sets `cancelled = true` and `finished_at = now()` in the database. The client never sees a terminal frame in that case — disconnection IS the terminal signal.

### Behaviors

- **Prompt assembly**: The server assembles a fresh system prompt from the live F4.2/F4.3 data (see research.md R4) plus all prior messages in this conversation (see research.md for multi-turn memory, matching FR-010a).
- **Persistence**: The user's message is inserted into `messages` before streaming begins. An assistant message is inserted with empty content at the same time, and its id is returned in the `start` frame. A single `UPDATE` finalizes the assistant message when streaming ends (success or cancellation).
- **Grounding degraded**: If the F4.2 inventory or F4.3 service registry query fails, the server still calls Ollama but with a system prompt that explicitly states "live network state could not be loaded for this turn" (FR-013). The response is not blocked.
- **Ollama unreachable**: The server emits a single `error` frame with a user-friendly message, finalizes the assistant message with `content = ''`, `finished_at = now()`, `cancelled = false`, and returns. Within SC-005's 5-second budget.

### Errors (before any frames are emitted)

- `404 Not Found` — conversation does not exist (plain JSON, not ndjson).
- `422 Unprocessable Entity` — request body fails validation (empty content, oversize).
- `503 Service Unavailable` — database unreachable (plain JSON).

Once streaming has begun (a `start` frame has been sent), all subsequent failures are reported via a terminal `error` frame in the ndjson stream rather than by changing the HTTP status code. The status remains `200 OK`.

---

## Summary table

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/chat/conversations/latest` | Load most recent conversation on page load |
| POST | `/chat/conversations` | Create a fresh conversation ("New chat" button) |
| GET | `/chat/conversations/{id}` | Load a specific conversation by id |
| POST | `/chat/conversations/{id}/messages` | Post a question and stream the advisor reply |

No DELETE / PATCH endpoints in v1. Conversation deletion and editing are out of scope.
