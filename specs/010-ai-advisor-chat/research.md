# Phase 0 Research: AI-Powered Advisor Chat

**Feature**: 010-ai-advisor-chat
**Date**: 2026-04-10

This document resolves the technical unknowns identified in the plan's Technical Context and records the decisions (with rationale and alternatives) that drive Phase 1 design.

---

## R1: Ollama API surface and streaming contract

### Decision

Use the Ollama native `POST /api/chat` endpoint with `"stream": true`. Parse the response as a stream of newline-delimited JSON objects where each chunk has the shape `{"message": {"role": "assistant", "content": "<token(s)>"}, "done": false}` and a final chunk with `"done": true` and stats (`prompt_eval_count`, `eval_count`, `total_duration`, etc.).

The backend calls Ollama with `httpx.AsyncClient.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0))`, iterates `response.aiter_lines()`, and yields the decoded text content of each chunk to the caller.

### Rationale

- The Ollama native `/api/chat` endpoint is the documented streaming interface and is stable across versions.
- Newline-delimited JSON is trivial to parse with `aiter_lines` and needs no extra SSE dependency.
- Setting `read=None` disables the idle-read timeout so long generations do not get killed by httpx. Connect/write/pool timeouts stay bounded so an unreachable Ollama is surfaced quickly (supports SC-005: failure in ≤5 s).
- Ollama also exposes an OpenAI-compatible `/v1/chat/completions` endpoint. We reject it because its SSE framing is more work to parse in Python and the native endpoint exposes Ollama-specific fields (eval stats, `done_reason`) that are useful for observability logging.

### Alternatives considered

- **OpenAI-compatible `/v1/chat/completions` with SSE**: Rejected — extra parsing cost, loses Ollama eval stats, no upside for a local-only deployment.
- **`ollama` Python SDK**: Rejected — adds a dependency that wraps httpx with an opinionated surface and is harder to hook into FastAPI's async streaming. `httpx` is already in `requirements.txt`.
- **Non-streaming request**: Rejected — directly violates FR-005 (progressive streaming) and SC-001 (≤ 3 s first-token visible).

---

## R2: FastAPI streaming response format from backend to browser

### Decision

Use FastAPI's `StreamingResponse` with `media_type="application/x-ndjson"` (newline-delimited JSON). Each line is one frame of the form:

```json
{"type": "token", "content": "Hello"}
{"type": "token", "content": " world"}
{"type": "done", "message_id": "uuid", "duration_ms": 2341}
{"type": "error", "message": "Ollama unreachable"}
```

The React client reads the response body with `fetch` + `response.body.getReader()` and a `TextDecoder`, splitting on newlines as chunks arrive.

### Rationale

- Matches the upstream Ollama format (ndjson), so the backend can forward frames with minimal re-framing.
- Works over a single HTTP POST, which is the simplest request shape for a question that carries a message body. SSE (`text/event-stream`) requires GET for `EventSource`, which forces tunneling message bodies through query parameters — awkward and size-constrained.
- Typed frame envelope (`type` field) lets the client distinguish tokens from completion and errors without hidden state, and gives us a clean hook for future frame types (e.g., `tool_call`, `citation`) without breaking the contract.
- `fetch` + `ReadableStream` is a first-class web API, works in all modern browsers, supports AbortController for cancellation.

### Alternatives considered

- **Server-Sent Events (`EventSource`)**: Rejected — requires GET, no native AbortController-style cancellation from the browser API (you have to close the EventSource object, but message-posting via GET query strings is awkward for free-text questions).
- **WebSocket**: Rejected — overkill for a unidirectional server→client stream with a single question per connection; adds connection lifecycle code on both sides.
- **Long polling**: Rejected — defeats the purpose of streaming.

---

## R3: Cancellation of in-flight advisor responses

### Decision

Implement cancellation via client-side `AbortController` → HTTP disconnect → backend detection via `await request.is_disconnected()` in a polling check inside the generator, which then cancels the Ollama httpx stream by breaking out of its async iteration (httpx closes the underlying connection and Ollama stops generating shortly after).

Persist the partial assistant message to Postgres on cancellation:

1. Create the assistant `Message` row immediately when the stream begins, with empty `content`.
2. As tokens stream in, accumulate them in a Python buffer AND emit ndjson frames to the client.
3. On normal completion OR on cancellation/disconnect, `UPDATE messages SET content = :buffer, cancelled = :bool, finished_at = now() WHERE id = :id` — one write per turn.

The cancellation poll happens every ~100 ms inside the streaming loop (not on every token — that's too noisy).

### Rationale

- Client-side `AbortController.abort()` on the stop button closes the TCP connection; FastAPI's `Request.is_disconnected()` returns `True` shortly after.
- One final DB write per turn keeps IO minimal and avoids the race of writing every token individually (which would be fine at single-admin scale but is unnecessary).
- Creating the assistant row up front gives us a stable `message_id` to emit in the `done` frame and lets the frontend optimistically render the message bubble before any tokens arrive.
- Satisfies FR-005a (visible stop, cancel propagates, partial saved) and edge case in spec.

### Alternatives considered

- **Explicit `POST /chat/conversations/{id}/cancel` endpoint**: Rejected — requires extra state (a per-stream cancellation token keyed somewhere), extra round-trip, and is redundant with TCP disconnect detection. The simpler path matches Constitution II (Simplicity).
- **WebSocket close frame for cancellation**: Rejected along with WebSockets in R2.
- **Write every token to DB**: Rejected — unnecessary write amplification. Single final write is simpler and fast enough.

---

## R4: Prompt assembly — format and content for grounding

### Decision

Assemble a single system message that contains three clearly-labeled sections in plain Markdown, followed by the full prior user/assistant exchange, followed by the new user question. Concrete shape:

```text
System (role=system):
  You are the Camelot network advisor. You answer questions about the user's
  home network based on the live state provided below. Always reference real
  devices and services by name. If the answer cannot be determined from the
  state below, say so clearly — do not guess.

  ## Devices ({n_online}/{n_total} online)
  - HOLYGRAIL (192.168.10.129) — role=server — ONLINE — tags: [media, ai]
  - Torrentbox (192.168.10.141) — role=torrent — ONLINE — tags: [vpn, arr]
  - NAS (192.168.10.105) — role=nas — OFFLINE — tags: [storage]
  ...

  ## Services ({n_healthy}/{n_total} healthy)
  - plex on HOLYGRAIL — HEALTHY — last_checked=2026-04-10T14:02:11Z
  - deluge on Torrentbox — UNHEALTHY (connection refused) — last_checked=...
  ...

  ## Recent alerts (last 24h, {n_alerts} total)
  - 2026-04-10T09:14:00Z — WARNING — deluge on Torrentbox — connection refused
  ...

  ## Recent events (last 24h, {n_events} total)
  - 2026-04-10T08:00:00Z — device_online — HOLYGRAIL
  ...

Prior messages (role=user / role=assistant, alternating from DB)
User (role=user): <new question>
```

The assembler module (`app/services/prompt_assembler.py`) exposes a single async function:

```python
async def assemble_chat_messages(
    db: AsyncSession,
    conversation_id: UUID,
    new_user_content: str,
) -> list[dict]:
    """Return the Ollama /api/chat `messages` array for this turn."""
```

It queries the existing F4.2/F4.3 tables directly (Device + DeviceAnnotation, Service + ServiceDefinition + HealthCheckResult, Alert, Event) rather than calling the `/ai-context` HTTP endpoint internally — direct DB access from inside the backend avoids an unnecessary intra-process HTTP hop.

### Rationale

- Markdown with labeled sections is a format Llama 3.1 8B handles well in practice; experiments in the F3.1 deployment showed it produces grounded, well-formatted answers when given this kind of layout.
- Putting device/service counts in the section headers gives the LLM a cheap way to answer "how many..." questions without having to count the list.
- Including `tags` on devices (populated by the F4.2 annotation system) means the admin's own descriptions flow into the prompt for free.
- Direct DB access is the project-consistent pattern — `ai_context.py` already does this and the Constitution's simplicity principle rejects internal HTTP hops.
- The existing `/ai-context` router is not reused as-is because it only returns devices + events — we need services and alerts too. The prompt assembler extends it conceptually. (Whether to replace `/ai-context` with a richer version or leave it alone is a task-level decision; both can coexist.)

### Alternatives considered

- **JSON-in-system-prompt** (passing a structured JSON blob): Rejected — Llama 3.1 8B reliably reads Markdown but can get tangled trying to "parse" raw JSON, and the answer quality is worse in practice. Markdown also reads better when the admin inspects logs.
- **Tool/function calling** (let the LLM decide when to query inventory/services): Rejected — adds significant complexity, Llama 3.1 8B's function-calling reliability at this scale is mediocre, and the single-admin use case doesn't need dynamic retrieval. Static per-turn context is simpler and sufficient per Constitution II.
- **Vector retrieval / RAG over a corpus of network state**: Rejected — massive overkill for ≤ 10 devices and ≤ 50 services. The full state easily fits in the context window.
- **Calling the `/ai-context` HTTP endpoint from inside the chat router**: Rejected — unnecessary intra-process HTTP hop; direct DB queries are simpler and faster.

---

## R5: Context window budget for Llama 3.1 8B

### Decision

No explicit context-trimming logic for v1. At the current scale (≤ 10 devices, ≤ 50 services, ≤ 50 recent alerts, ≤ 100 recent events), the fully-assembled system prompt stays well under 8K tokens even in the worst case. With Llama 3.1 8B's 128K window there is ~16× headroom, and conversations would need hundreds of long turns before getting close.

FR-012 is satisfied by a defensive length check in `prompt_assembler.py`:

```python
MAX_PROMPT_CHARS = 60_000  # very rough ≈ 15K tokens, well under 128K
if total_chars > MAX_PROMPT_CHARS:
    log.warning("prompt_too_large", chars=total_chars)
    # trim oldest conversation turns first, keep system context intact
```

Trimming is a fallback, not a routine operation. It logs when it fires so we know if it's actually happening.

### Rationale

- The Constitution's simplicity principle (II) says don't build for hypothetical scale. A home network isn't going to hit context limits.
- A simple character-based heuristic is the obvious default — tokenizing just to count is overkill when we have 16× headroom.
- Logging the trigger gives us observability (Constitution V) if the assumption ever breaks.

### Alternatives considered

- **Token-accurate counting via `tiktoken` or the Ollama tokenizer**: Rejected — adds a dependency and compute cost for a check that effectively never fires.
- **Per-turn summarization of older messages**: Rejected — premature. Clarification Q4 explicitly kept full multi-turn memory and no windowing for v1.

---

## R6: Database schema patterns for Conversation and Message

### Decision

Two tables, created by Alembic migration `003_chat_conversations.py`:

**`conversations`**
- `id` UUID PK (generated by Postgres `gen_random_uuid()` — `pgcrypto` extension is already enabled from F4.2)
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now() — bumped on every message insert
- `title` TEXT NULL — future-friendly (e.g., "first user message as title"); not populated in v1 but the column exists so the future feature doesn't need a second migration

**`messages`**
- `id` UUID PK
- `conversation_id` UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE
- `role` TEXT NOT NULL CHECK (role IN ('user', 'assistant'))
- `content` TEXT NOT NULL DEFAULT ''
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- `finished_at` TIMESTAMPTZ NULL — NULL while assistant message is streaming, set on completion or cancellation
- `cancelled` BOOLEAN NOT NULL DEFAULT FALSE
- INDEX `ix_messages_conversation_id_created_at` (conversation_id, created_at)

"Latest conversation" query for FR-006a: `SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 1`.

### Rationale

- UUIDs match what the existing F4.2/F4.3 schemas already use (the project is on UUIDs end-to-end).
- `ON DELETE CASCADE` for the FK is the obvious default at single-admin scale — deleting a conversation should delete its messages.
- Composite index on `(conversation_id, created_at)` makes the "fetch all messages in a conversation in order" query O(log n) to locate + sequential scan, which is the hot path.
- The `title` column is added now with a NULL default because adding a column later is cheap but changing the table shape in migration 004 just to add it is slightly more friction. It costs nothing to include and satisfies YAGNI's "if it's one line that might be useful, just add it."
- `finished_at` + `cancelled` together give enough state to reconstruct "was this a clean completion or a cancelled one" without a separate enum.

### Alternatives considered

- **`status` enum column instead of `finished_at` + `cancelled`**: Rejected — two columns are cheaper than introducing a Postgres enum type that has to be managed in its own migration.
- **No `title` column**: Rejected — adding it later would need its own migration. It's effectively free to add now.
- **JSONB blob for the entire conversation**: Rejected — loses the ability to query/paginate messages, and the existing schema pattern in the project is relational.

---

## R7: Ollama reachability and configuration

### Decision

Add two new env-var-backed settings in `app/config.py`:

```python
OLLAMA_BASE_URL: str = "http://ollama:11434"       # container-network default
OLLAMA_MODEL: str = "llama3.1:8b"                  # configurable default
```

Loaded via `pydantic-settings` (already in `requirements.txt`). Overridable at runtime via `.env` or Docker Compose environment.

At startup in `main.py`'s lifespan, perform a best-effort `GET {OLLAMA_BASE_URL}/api/version` with a short (2 s) timeout. If it fails, log a warning but do NOT crash — the advisor is useful for inventory/services browsing even when the chat is broken. The chat endpoint itself returns the FR-009 user-friendly failure message when a request hits an unreachable Ollama.

### Rationale

- Matches Clarification on model configurability (env var, not UI picker, per simplicity) and Constitution II.
- Matches the existing `advisor/docker-compose.yml` pattern — it already runs on the HOLYGRAIL Compose network alongside Ollama, so `http://ollama:11434` resolves container-to-container.
- Best-effort startup check is pure observability (Constitution V) — it doesn't gate anything, it just surfaces the problem in logs.
- Single default model matches the F3.1 Ollama deployment which installed Llama 3.1 8B as the default.

### Alternatives considered

- **Hard-coded URL/model**: Rejected — we want to be able to swap models or point at a different Ollama instance without code changes, and `pydantic-settings` is already loaded.
- **Gate backend startup on Ollama availability**: Rejected — advisor dashboard usability shouldn't depend on the LLM being up.
- **UI model picker**: Rejected at clarify time as over-engineered for v1.

---

## R8: React streaming consumption pattern

### Decision

In `advisor/frontend/src/services/chat.ts`, expose a single async generator that takes a conversation id and user text and yields frames from the backend ndjson stream:

```typescript
export async function* streamChatMessage(
  conversationId: string,
  userText: string,
  signal: AbortSignal,
): AsyncGenerator<ChatFrame, void, unknown> {
  const response = await fetch(
    `/chat/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: userText }),
      signal,
    },
  );
  if (!response.ok || !response.body) {
    throw new Error(`chat stream failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newlineIdx;
    while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newlineIdx).trim();
      buffer = buffer.slice(newlineIdx + 1);
      if (line) yield JSON.parse(line) as ChatFrame;
    }
  }
}
```

The `Chat.tsx` page holds an `AbortController` in a ref; the stop button calls `controller.abort()`, which throws `AbortError` inside the generator loop. The page catches that, marks the current assistant message as cancelled in local state, and the backend's final DB write (per R3) makes the state durable on refresh.

### Rationale

- Async generator is the idiomatic JS/TS shape for "iterate over streamed items" and maps cleanly onto the ndjson frames.
- `AbortController` is the standard web API for cancelling `fetch`, and the backend already detects disconnect via R3.
- Keeping the stream parser in `services/chat.ts` means the React component just awaits frames and updates state — no stream logic in the view layer.

### Alternatives considered

- **EventSource**: Rejected (see R2).
- **Third-party streaming client library** (e.g., `@microsoft/fetch-event-source`): Rejected — adds a dependency for code we can write in ~30 lines.
- **Parse on the backend into SSE**: Rejected — extra layer that buys nothing.

---

## R9: Test strategy (post-implementation, per Constitution IV)

### Decision

**Backend** (pytest + pytest-asyncio + httpx AsyncClient):

- `test_chat_api.py`
  - `test_get_latest_returns_null_when_no_conversations`
  - `test_post_new_conversation_creates_row`
  - `test_post_message_streams_ndjson_frames` — mocks `ollama_client.stream_chat` to yield fixed tokens, asserts frames shape and ordering
  - `test_post_message_persists_user_and_assistant_messages`
  - `test_post_message_saves_partial_on_cancel` — triggers `request.is_disconnected()` via a mocked request, asserts `cancelled=True` and `content` is the partial buffer
  - `test_post_message_returns_friendly_error_when_ollama_unreachable` — `ollama_client.stream_chat` raises `httpx.ConnectError`, assert one `{"type":"error"}` frame
- `test_prompt_assembler.py`
  - `test_devices_section_lists_all_with_online_state`
  - `test_services_section_marks_unhealthy`
  - `test_alerts_section_includes_last_24h_only`
  - `test_prior_messages_are_appended_in_order`
  - `test_new_user_message_is_last`
- `test_ollama_client.py`
  - `test_stream_chat_yields_tokens_from_ndjson` — uses `respx` or `httpx.MockTransport` to fake Ollama
  - `test_stream_chat_surfaces_connection_error`

**Frontend** (Vitest + @testing-library/react + MSW for fetch mocking):

- `ChatThread.test.tsx`
  - renders user and assistant messages with distinct roles
  - appends streamed tokens to the active assistant bubble
  - stop button calls `AbortController.abort()` and marks the assistant message as cancelled
  - displays friendly error when the error frame arrives

### Rationale

- Matches Constitution IV: tests after, integration-style where possible, minimal mocking.
- The Ollama client is the only true external boundary — mocking it in tests (via `httpx.MockTransport` / `respx`) is appropriate.
- Database is NOT mocked — tests run against the existing Postgres test setup in `advisor/backend/tests/conftest.py` (the project already uses real async Postgres in tests per the existing pattern in `test_devices_api.py` etc., so we inherit that).

### Alternatives considered

- **Full end-to-end test against a running Ollama**: Rejected — makes the test suite dependent on a live GPU backend, flaky, and slow. Covered manually in `quickstart.md`.
- **Vitest snapshot tests of streaming state**: Rejected — snapshot tests of async state machines are brittle; explicit assertions are clearer.

---

## Summary of decisions

| ID | Area | Decision |
| --- | --- | --- |
| R1 | Ollama API | Native `POST /api/chat` with ndjson streaming via httpx |
| R2 | Backend→browser | FastAPI `StreamingResponse` with typed ndjson frames |
| R3 | Cancellation | Client AbortController → `is_disconnected()` → single final DB write |
| R4 | Prompt assembly | Markdown sections (Devices / Services / Alerts / Events) + full prior exchange |
| R5 | Context budget | No explicit trimming in v1; fallback character heuristic with warning log |
| R6 | DB schema | Two tables (conversations, messages), UUID PKs, cascade delete |
| R7 | Config | Env vars `OLLAMA_BASE_URL`, `OLLAMA_MODEL`; best-effort startup reachability check |
| R8 | Frontend stream | `fetch` + `ReadableStream` async generator, `AbortController` for stop |
| R9 | Tests | Post-impl pytest + Vitest; mock only Ollama boundary; manual quickstart for E2E |

All `NEEDS CLARIFICATION` in the Technical Context are resolved.
