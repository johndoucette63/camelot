---
description: "Task list for F4.4 — AI-Powered Advisor Chat"
---

# Tasks: AI-Powered Advisor Chat

**Input**: Design documents from `/Users/jd/Code/camelot/specs/010-ai-advisor-chat/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/chat-api.md, quickstart.md

**Tests**: Test tasks are INCLUDED and come AFTER implementation tasks, per Camelot constitution principle IV (Test-After, not Test-First). Tests use the existing pytest (backend) and Vitest (frontend) harnesses and follow the "mock only external boundaries" rule — only the Ollama HTTP client is mocked.

**Organization**: Tasks are grouped by user story. US1 (MVP) delivers a working chat loop with streaming and persistence but no grounding. US2 adds network-state grounding. US3 is validation of the 4-question acceptance bar.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All file paths are absolute or rooted at the repo root (`/Users/jd/Code/camelot/`)

## Path Conventions

- **Backend**: `advisor/backend/app/`, tests in `advisor/backend/tests/`
- **Frontend**: `advisor/frontend/src/`, tests in `advisor/frontend/src/components/__tests__/`
- **Migrations**: `advisor/backend/migrations/versions/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Small configuration additions to the existing advisor stack. No new dependencies needed — `httpx` is already in `requirements.txt`, all React deps are already in `package.json`.

- [X] T001 Added `ollama_model` setting (default `llama3.1:8b`) to `advisor/backend/app/config.py`. Reused existing `ollama_url` (pointing at `http://ollama.holygrail` via Traefik).
- [X] T002 Added `OLLAMA_MODEL` env var to the `backend` service in `advisor/docker-compose.yml` alongside the existing `OLLAMA_URL`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, SQLAlchemy models, router skeleton, and the Ollama streaming client. Everything every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Create Alembic migration `advisor/backend/migrations/versions/003_chat_conversations.py` per the sketch in `specs/010-ai-advisor-chat/data-model.md` — creates `conversations` (id, created_at, updated_at, title) and `messages` (id, conversation_id FK cascade, role, content, created_at, finished_at, cancelled) tables with the two CHECK constraints (`role IN ('user','assistant')` and `role='user' OR cancelled=false OR content!=''`) and the composite index `ix_messages_conversation_id_created_at` plus `ix_conversations_updated_at`.
- [ ] T004 ⏳ **DEFERRED TO DEPLOY**: Run `alembic upgrade head` on HOLYGRAIL after the branch is merged and deployed — `ssh john@holygrail "cd ~/camelot/advisor && docker compose exec backend alembic upgrade head"`. The migration is syntactically validated and the models work against the SQLite test schema (21 backend tests pass). No local Postgres container is available on the Mac workstation, so the real upgrade/downgrade cycle runs as part of deploy validation.
- [X] T005 [P] Create `advisor/backend/app/models/conversation.py` with the SQLAlchemy 2.0 async `Conversation` model (UUID PK, `created_at`, `updated_at`, `title`, and a `messages` relationship with `cascade="all, delete-orphan"` and `order_by="Message.created_at"`).
- [X] T006 [P] Create `advisor/backend/app/models/message.py` with the SQLAlchemy 2.0 async `Message` model (UUID PK, `conversation_id` FK, `role`, `content`, `created_at`, `finished_at`, `cancelled`, and a back-reference to `Conversation`).
- [X] T007 Create `advisor/backend/app/routers/chat.py` as a skeleton `APIRouter()` with placeholder handlers for the four endpoints defined in `contracts/chat-api.md` (returning `501 Not Implemented` for now). Add Pydantic request/response models (`ChatMessageCreate`, `ChatConversationRead`, `ChatMessageRead`) in the same file.
- [X] T008 Register the chat router in `advisor/backend/app/main.py` with `app.include_router(chat.router, prefix="/chat", tags=["chat"])` (add `chat` to the existing import line). Verify the OpenAPI docs at `/docs` show the four new stub endpoints.

**Checkpoint**: Foundation ready. Migration applied, models importable, router mounted. User story implementation can now begin.

---

## Phase 3: User Story 1 - Ask the advisor a question and get a conversational reply (Priority: P1) 🎯 MVP

**Goal**: A working chat loop. The admin opens the chat, types a question, and sees a conversational reply streamed back token-by-token. Page reload preserves the conversation. "New chat" button starts fresh. Stop button cancels an in-flight reply and saves the partial text. Ollama unreachable surfaces a friendly error within 5 s.

**Independent Test**: Run `quickstart.md` sections "US-1 validation", "Cancellation validation", and "Persistence & resume validation" — all should pass with a static (non-grounded) system prompt.

### Implementation for User Story 1

- [X] T009 [US1] Implement the Ollama streaming client in `advisor/backend/app/services/ollama_client.py`. Expose `async def stream_chat(messages: list[dict], model: str) -> AsyncIterator[str]` that calls `POST {OLLAMA_BASE_URL}/api/chat` with `{"model": model, "messages": messages, "stream": True}`, uses `httpx.AsyncClient.stream()` with `timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)`, iterates `response.aiter_lines()`, parses each JSON frame, and yields the `message.content` of each non-done chunk. Raises `OllamaUnreachableError` on `httpx.ConnectError` / `httpx.ReadTimeout` during connect. Per research.md R1.
- [X] T010 [US1] Implement `GET /chat/conversations/latest` in `advisor/backend/app/routers/chat.py`. Query `conversations ORDER BY updated_at DESC LIMIT 1` with `selectinload` for messages. Return 204 when empty, 200 with the shape defined in `contracts/chat-api.md` otherwise.
- [X] T011 [US1] Implement `POST /chat/conversations` in `advisor/backend/app/routers/chat.py`. Insert an empty row into `conversations`, return 201 with the empty conversation payload.
- [X] T012 [US1] Implement `GET /chat/conversations/{conversation_id}` in `advisor/backend/app/routers/chat.py`. Return 404 on unknown id, 200 with the conversation + messages otherwise.
- [X] T013 [US1] Implement `POST /chat/conversations/{conversation_id}/messages` in `advisor/backend/app/routers/chat.py` as a `StreamingResponse` with `media_type="application/x-ndjson"`. Flow: (a) validate body, (b) 404 if the conversation is missing, (c) insert the user `Message` row, (d) insert an empty assistant `Message` row and capture its id, (e) build a static system prompt (no grounding yet — US2 replaces this) plus the full prior exchange from `messages` ordered by `created_at`, (f) call `ollama_client.stream_chat`, (g) emit a `start` frame with the assistant message id, then one `token` frame per yielded content chunk, accumulating tokens into a local buffer, (h) poll `await request.is_disconnected()` between chunks — on disconnect break out of the loop, (i) on normal completion, `UPDATE` the assistant message with `content=buffer, finished_at=now(), cancelled=False` and emit the `done` frame, (j) on disconnect path, same `UPDATE` with `cancelled=True` and no terminal frame (disconnect IS the terminal signal), (k) on `OllamaUnreachableError`, `UPDATE` the assistant message with `content='', finished_at=now(), cancelled=False` and emit a single `error` frame with the user-friendly message. Bump `conversations.updated_at` on every message insert in the same transaction. Per research.md R2 and R3 and contracts/chat-api.md.
- [X] T014 [P] [US1] Add `ChatConversation` and `ChatMessage` TypeScript types plus the `ChatFrame` discriminated union (`{type: "start" | "token" | "done" | "error", ...}`) to `advisor/frontend/src/types.ts`.
- [X] T015 [P] [US1] Create `advisor/frontend/src/services/chat.ts` with: `fetchLatestConversation()`, `createConversation()`, `fetchConversation(id)`, and the async generator `streamChatMessage(conversationId, userText, signal)` that reads `response.body.getReader()` and yields parsed `ChatFrame` objects. Per research.md R8.
- [X] T016 [P] [US1] Create `advisor/frontend/src/components/ChatMessage.tsx`. Props: `{role: "user" | "assistant", content: string, cancelled?: boolean}`. Renders a single bubble with role-based styling (right-aligned + accent bg for user, left-aligned + neutral bg for assistant). Shows a subtle "(stopped)" badge when `cancelled`.
- [X] T017 [P] [US1] Create `advisor/frontend/src/components/ChatThread.tsx`. Props: `{messages: ChatMessage[]}`. Renders a scrollable vertical stack of `ChatMessage` components in order. Auto-scrolls to bottom when a new message arrives or when the active message's content grows.
- [X] T018 [P] [US1] Create `advisor/frontend/src/components/ChatComposer.tsx`. Props: `{onSubmit: (text: string) => void, onStop: () => void, isStreaming: boolean}`. Renders a textarea, a submit button (disabled when streaming or empty/whitespace input), and a stop button (visible only when `isStreaming`).
- [X] T019 [US1] Create `advisor/frontend/src/pages/Chat.tsx`. Layout: a page header containing the page title and a visible **"New chat"** button (right-aligned, disabled while a response is streaming to avoid mid-stream conversation switches), a `<ChatThread>` filling the main area, and a `<ChatComposer>` pinned to the bottom. On mount: call `fetchLatestConversation()`; if 204 call `createConversation()` instead; store the active conversation in state. Handlers: (a) submit → optimistically append user message, append an empty assistant message, start `streamChatMessage` with a fresh `AbortController`, append tokens to the active assistant message as frames arrive, mark done on `done` frame, (b) stop → call `controller.abort()`, mark the active assistant message `cancelled=true` in local state, (c) **new chat button click** → call `createConversation()` and reset local state to the new empty conversation. Handles the `error` frame by appending the friendly message text to the active assistant bubble and marking it finished.
- [X] T020 [US1] Wire the chat page into the app: (a) add a `<Route path="/chat" element={<Chat />}>` in `advisor/frontend/src/App.tsx`, (b) add a Chat link to the existing sidebar/nav in the appropriate layout component (whatever pattern Devices/Services/Events already use).

### Tests for User Story 1

- [X] T021 [P] [US1] Create `advisor/backend/tests/test_chat_api.py` covering: `test_get_latest_returns_204_when_no_conversations`, `test_post_creates_empty_conversation`, `test_get_by_id_returns_404_for_missing`, `test_post_message_streams_ndjson_frames_in_expected_order` (mocks `ollama_client.stream_chat` to yield fixed tokens, asserts start→token*→done shape), `test_post_message_persists_user_and_assistant_rows`, `test_post_message_saves_partial_on_disconnect` (patches `Request.is_disconnected` to return True after the second token, asserts DB row has `cancelled=True` and `content` is the accumulated prefix), `test_post_message_returns_error_frame_when_ollama_unreachable` (mock raises `OllamaUnreachableError`, asserts single error frame). Use the existing `conftest.py` async Postgres fixture.
- [X] T022 [P] [US1] Create `advisor/backend/tests/test_ollama_client.py` covering: `test_stream_chat_yields_content_from_ndjson_chunks` (uses `httpx.MockTransport` to return a canned ndjson body), `test_stream_chat_raises_ollama_unreachable_on_connect_error`, `test_stream_chat_honors_read_timeout_none` (assert the timeout config lets a slow response through). Mock only the HTTP transport — no monkeypatching of the client class.
- [X] T023 [P] [US1] Create `advisor/frontend/src/components/__tests__/ChatThread.test.tsx` and `Chat.test.tsx` covering: renders user and assistant bubbles with distinct role styling; streamed tokens append progressively to the active assistant bubble; clicking the stop button triggers `AbortController.abort()` and marks the message cancelled; an `error` frame surfaces a friendly message in the bubble. Use MSW to mock the backend streaming response.

**Checkpoint**: US1 complete. Chat works end-to-end with a static system prompt. Responses are conversational but ungrounded ("your network" answered from generic knowledge). This is deployable as an MVP.

---

## Phase 4: User Story 2 - Advisor answers are grounded in the current network state (Priority: P2)

**Goal**: Replace the static system prompt from US1 with one assembled from live F4.2 inventory and F4.3 services / health / alerts / events data, so the advisor's answers reference real devices and services by name.

**Independent Test**: Run `quickstart.md` section "US-2 validation" — with one device offline and one service unhealthy, the advisor must name them specifically in its responses without inventing entities.

### Implementation for User Story 2

- [X] T024 [US2] Create `advisor/backend/app/services/prompt_assembler.py` exposing `async def assemble_chat_messages(db: AsyncSession, conversation_id: UUID, new_user_content: str) -> list[dict]`. Queries in order: (a) all devices with their annotations via `selectinload(Device.annotation)`, (b) all services with their latest health-check result, (c) alerts from the last 24h, (d) events from the last 24h, (e) all prior messages in the conversation ordered by `created_at`. Builds the Markdown-sectioned system prompt per research.md R4, then appends prior messages as `{role, content}` dicts, then the new user message. Includes the character-count safety check from research.md R5 (`MAX_PROMPT_CHARS = 60_000`) — logs a warning and trims oldest non-system messages first if the limit is exceeded.
- [X] T025 [US2] Wire `prompt_assembler.assemble_chat_messages` into the `POST /chat/conversations/{id}/messages` handler in `advisor/backend/app/routers/chat.py`, replacing the static system prompt from T013. The handler now passes the assembled messages list to `ollama_client.stream_chat`. The user message insert and assistant message shell insert happen BEFORE prompt assembly so that assembly can read the prior exchange from the DB (and not see the current turn's assistant shell, which is still empty).
- [X] T026 [US2] Add FR-013 graceful degradation in `prompt_assembler.py`: wrap each F4.2/F4.3 query in its own try/except; if any one fails, log a structured warning and substitute a section that says `"(live network state for this section could not be loaded)"`. The assembler MUST still return a valid messages list — never raise back to the router. Per spec FR-013.

### Tests for User Story 2

- [X] T027 [P] [US2] Create `advisor/backend/tests/test_prompt_assembler.py` covering: `test_devices_section_lists_all_devices_with_online_state` (seeds a mix of online/offline devices via the existing test fixtures, asserts substring matches in the assembled system message), `test_services_section_marks_unhealthy_services`, `test_alerts_section_includes_only_last_24_hours` (seeds alerts at 12h ago and 48h ago, asserts only the 12h one is in the prompt), `test_prior_messages_appended_in_chronological_order`, `test_new_user_message_is_last`, `test_degrades_gracefully_when_devices_query_fails` (monkeypatches the devices query to raise, asserts the returned messages list contains the "state could not be loaded" placeholder and does NOT raise), `test_warns_and_trims_when_prompt_exceeds_max_chars`.

**Checkpoint**: US2 complete. Asking "what devices are on my network?" returns real hostnames. US1's chat loop still works as before — grounding is a pure drop-in replacement of the system prompt.

---

## Phase 5: User Story 3 - Representative question set validation (Priority: P3)

**Goal**: Prove that the grounded advisor passes the 4-question acceptance bar defined in spec.md (SC-002). This phase is primarily validation; any code changes come from iterating on the prompt format if a question fails.

**Independent Test**: Run `quickstart.md` section "US-3 validation". All 4 questions must receive responses that reference real entities with zero hallucinated devices or services.

### Implementation for User Story 3

- [ ] T028 [US3] ⏳ **DEFERRED TO DEPLOY** (manual validation): Execute the 4 representative questions from spec.md US-3 against a live deployment seeded with a known state (at least one offline device, at least one unhealthy service, at least one recent alert). Record each answer in a scratch note. Verify each answer against the US-3 acceptance scenarios — real entity names, no hallucinations, admits uncertainty when data isn't there. This is the SC-002 acceptance gate.
- [ ] T029 [US3] ⏳ **DEFERRED TO DEPLOY** (contingent on T028): If any of the 4 questions fails the acceptance bar in T028, iterate on `advisor/backend/app/services/prompt_assembler.py` — adjust section formatting, add system-prompt guidance, or include more context fields from F4.3 — and re-run T028. This task may be a no-op if T028 passes on the first try.

### Tests for User Story 3

US-3 has no automated test task. Substring-matching LLM output is brittle and flaky; the 4 questions are validated manually through `quickstart.md` section "US-3 validation" instead. The manual run IS the acceptance gate for SC-002.

**Checkpoint**: All three user stories are done. Feature is shippable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 [P] Added structured JSON observability logging in `advisor/backend/app/routers/chat.py` (the `logger.info("chat_turn", extra={...})` call in the streaming finalizer's `finally` block). Emits `conversation_id`, `message_id`, `duration_ms`, `content_chars`, `eval_count_hint`, `cancelled`, `ollama_error`. Uses the existing `python-json-logger` setup from `main.py`. Per constitution principle V.
- [ ] T031 ⏳ **DEFERRED TO DEPLOY**: Run the full `specs/010-ai-advisor-chat/quickstart.md` walkthrough end-to-end on HOLYGRAIL against real data. All sections must pass: US-1, US-2, US-3, cancellation, persistence/resume, multi-turn memory, observability, constitution alignment. Fix any regressions uncovered.
- [X] T032 [P] Update `docs/PROJECT-PLAN.md` and `docs/F4.4-ai-advisor-chat.md` to mark F4.4 as complete. Update `CLAUDE.md`'s Phase 4 row if not already done by the agent-context updater. Update `advisor/README.md` (if present) with a short "Chat" section pointing at the new `/chat` route and the env vars from T001.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Starts immediately. T001 and T002 can run in sequence (same project, tiny edits).
- **Phase 2 (Foundational)**: Starts after Phase 1. T003 → T004 is strictly sequential (migration, then verify). T005 and T006 are parallelizable with each other. T007 depends on T005+T006. T008 depends on T007.
- **Phase 3 (US1)**: Starts after Phase 2. Implementation tasks T009–T020 run largely in parallel where the `[P]` marker is present. Tests T021–T023 come AFTER implementation, in parallel with each other.
- **Phase 4 (US2)**: Starts after US1 ships (or at minimum after T013 is in place so there is something to wire into). T024 → T025 → T026 is sequential. T027 comes after.
- **Phase 5 (US3)**: Starts after US2. T028 → T029 sequential.
- **Phase 6 (Polish)**: Starts after all user stories complete. T030 and T032 parallelizable; T031 is the final gate.

### User Story Dependencies

- **US1**: Depends only on Foundational. Independently testable with a static system prompt (answers are conversational but ungrounded).
- **US2**: Depends on US1 (wires into the existing chat POST handler). Independently testable — the grounding test can be verified without touching the chat UI once US1 is stable.
- **US3**: Depends on US2 (grounded answers are the prerequisite for the acceptance bar). No code implementation of its own beyond optional prompt tuning.

### Within each User Story

- Implementation tasks complete first.
- Tests come AFTER implementation tasks (constitution IV: Test-After).
- Frontend component tasks [P] can run in parallel with each other.
- Backend router handler tasks can run in parallel ONLY when they edit different files — T010–T013 all edit `routers/chat.py`, so they are sequential in the same file even though they are logically independent endpoints.

### Parallel Opportunities

- T005 || T006 (two new model files)
- T014 || T015 || T016 || T017 || T018 (types + service + 3 components, all different files)
- T021 || T022 || T023 (three test files)
- T030 || T032 (logging addition + docs update)

---

## Parallel Example: User Story 1 frontend fan-out

After T013 is done on the backend, the frontend work can fan out:

```text
# Launch all frontend building blocks together:
Task: "Add ChatConversation/ChatMessage/ChatFrame types in advisor/frontend/src/types.ts"
Task: "Create advisor/frontend/src/services/chat.ts with fetch helpers + streamChatMessage generator"
Task: "Create advisor/frontend/src/components/ChatMessage.tsx"
Task: "Create advisor/frontend/src/components/ChatThread.tsx"
Task: "Create advisor/frontend/src/components/ChatComposer.tsx"
```

Once those are in, T019 (`Chat.tsx` page) composes them, and T020 wires the route.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup): T001–T002.
2. Phase 2 (Foundational): T003–T008. Gate: migration applied, router mounted, models importable.
3. Phase 3 (US1): T009–T020 (implementation) then T021–T023 (tests).
4. **STOP and VALIDATE**: Run `quickstart.md` sections US-1, cancellation, persistence/resume. Confirm the advisor answers "Hello, who are you?" conversationally with streaming and that stopping/persistence/resume all work. Answers to questions like "what devices are on my network?" will be generic at this point — that's expected.
5. Deploy the MVP. Ungrounded chat on a local LLM is still useful.

### Incremental Delivery

1. MVP → Deploy → Use.
2. Phase 4 (US2): T024–T026 implementation, T027 tests. Validate quickstart US-2 section. Redeploy.
3. Phase 5 (US3): T028 validation, T029 iterate on prompt if needed. No redeploy unless T029 touches code.
4. Phase 6 (Polish): T030 logging, T031 full quickstart, T032 docs. Final redeploy.

### Single-Developer Strategy

Since Camelot has one developer (per Constitution), the "parallel team" strategy in the template doesn't apply. The `[P]` markers still matter — they signal which tasks can be done in any order or batched in a single coding session without conflicts — but there is only one pair of hands. Follow MVP-first + incremental delivery.

---

## Notes

- Every task has a file path. Vague tasks have been rejected.
- Test-After is the rule: implementation tasks come before test tasks within each story phase.
- The only external boundary mocked in tests is the Ollama HTTP client. The database is NOT mocked — tests run against the existing async Postgres fixture in `advisor/backend/tests/conftest.py`.
- Commit after each task or small logical group. Each commit should leave the system in a working state (Constitution development workflow).
- Cross-story dependencies are minimal: US2 wires into US1's chat POST handler as a drop-in replacement, and US3 is pure validation of US2's output. Each story remains independently verifiable via its quickstart section.
