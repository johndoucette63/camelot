# Tasks: Advisor Learnings & Curated Notes

**Input**: Design documents from `/specs/012-advisor-learnings-notes/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included per Constitution Principle IV (Test-After) — tests follow implementation within each story phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Database schema, models, schemas, and shared client code that all user stories depend on.

- [x] T001 [P] Create Note SQLAlchemy model with target_type/target_id polymorphic pattern, body, pinned, title, tags, timestamps in advisor/backend/app/models/note.py
- [x] T002 [P] Create RejectedSuggestion SQLAlchemy model with content_hash (unique), conversation_id FK (SET NULL), created_at in advisor/backend/app/models/rejected_suggestion.py
- [x] T003 [P] Create Pydantic request/response schemas (NoteCreate, NoteUpdate, NoteResponse, NoteListResponse, SuggestionResponse, RejectedSuggestionCreate) in advisor/backend/app/schemas/note.py
- [x] T004 [P] Add Note and NoteSuggestion TypeScript types to advisor/frontend/src/types.ts
- [x] T005 [P] Create notes API service (fetchNotes, createNote, updateNote, deleteNote, fetchTags, rejectSuggestion, suggestNotes) in advisor/frontend/src/services/notes.ts
- [x] T006 Create Alembic migration 005_advisor_notes.py with notes table (columns, CHECK constraint, 3 indexes), rejected_suggestions table (unique hash index), and 3 seed playbook entries in advisor/backend/migrations/versions/005_advisor_notes.py
- [x] T007 Import Note and RejectedSuggestion models in advisor/backend/migrations/env.py to enable Alembic autogenerate detection

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend CRUD endpoints and cascade logic that MUST be complete before any user story frontend work.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T008 Implement Notes CRUD router with list (GET, filtered by target_type/target_id/tag), create (POST, with 2KB validation and pinned cap enforcement), update (PATCH), and delete (DELETE) endpoints in advisor/backend/app/routers/notes.py
- [x] T009 Add tags autocomplete endpoint (GET /api/notes/tags) returning distinct tags from playbook notes, sorted alphabetically, in advisor/backend/app/routers/notes.py
- [x] T010 Add rejected-suggestions endpoint (POST /api/notes/rejected-suggestions) with SHA-256 content hashing and idempotent upsert in advisor/backend/app/routers/notes.py
- [x] T011 Register notes router with prefix "/api/notes" in advisor/backend/app/main.py
- [x] T012 [P] Add application-level cascade delete for notes (target_type='device') when a device is deleted in the existing device deletion code path
- [x] T013 [P] Add application-level cascade delete for notes (target_type='service') when a service definition is deleted in the existing service deletion code path

**Checkpoint**: Notes CRUD API is functional. All endpoints respond correctly. Seed data is queryable. Ready for frontend integration.

---

## Phase 3: User Story 1 — Record and Reference Device Notes (Priority: P1) MVP

**Goal**: Admin can create notes on devices and have the advisor reference them in chat with source attribution.

**Independent Test**: Create a device note, start a fresh chat session, ask about that device — advisor references the note and attributes the source.

### Implementation for User Story 1

- [x] T014 [P] [US1] Create reusable NotesList component (list, add, edit, delete, pin toggle) that accepts target_type and target_id props in advisor/frontend/src/components/NotesList.tsx
- [x] T015 [US1] Add notes tab/section to DeviceAnnotationModal showing NotesList for the selected device (target_type='device', target_id=device.id) in advisor/frontend/src/components/DeviceAnnotationModal.tsx
- [x] T016 [US1] Add _load_notes_section() function in prompt_assembler.py that queries all pinned notes (always included) and unpinned notes (included under budget), formats them as labeled Markdown sections (e.g., "### Device: NAS (192.168.10.105)"), and wraps in _safe_load() for graceful degradation in advisor/backend/app/services/prompt_assembler.py
- [x] T017 [US1] Add note attribution instruction to SYSTEM_PREAMBLE ("When referencing knowledge from admin notes, cite the source") and insert the notes section call between Active Alerts and Recent Events in the assemble_chat_messages() function in advisor/backend/app/services/prompt_assembler.py

### Tests for User Story 1

- [x] T018 [P] [US1] Write pytest tests for notes CRUD API: create device note, list notes by target, update note body/pinned, delete note, validate empty body rejection, validate 2KB limit, validate pinned cap (409), validate cascade delete in advisor/backend/tests/test_notes_api.py
- [x] T019 [P] [US1] Write pytest tests for prompt assembler notes section: pinned notes always included, unpinned notes trimmed under budget pressure, graceful degradation when notes query fails, attribution labels present in output in advisor/backend/tests/test_prompt_assembler_notes.py

**Checkpoint**: Device notes are fully functional end-to-end. Admin can create notes on devices and the advisor references them with attribution. This is the MVP.

---

## Phase 4: User Story 2 — Cross-Cutting Playbook Entries (Priority: P2)

**Goal**: Dedicated Playbook page with titled entries, free-form tags with autocomplete, and tag-based filtering. Playbook entries appear in advisor grounding context.

**Independent Test**: Create a playbook entry with tags, filter by tag in the UI, ask the advisor a general network question — it references the playbook entry.

### Implementation for User Story 2

- [x] T020 [P] [US2] Create PlaybookModal component (create/edit form with title, Markdown body textarea, tag input with autocomplete from GET /api/notes/tags, pinned toggle) in advisor/frontend/src/components/PlaybookModal.tsx
- [x] T021 [US2] Create Playbook page with entry list (title, tags as badges, pinned indicator, timestamps), tag filter bar, and "New entry" button that opens PlaybookModal in advisor/frontend/src/pages/Playbook.tsx
- [x] T022 [US2] Add /playbook route and "Playbook" nav link (between Events and Chat) in advisor/frontend/src/App.tsx

### Tests for User Story 2

- [x] T023 [US2] Write Vitest component test for Playbook page: renders seed entries, tag filter works, create/edit/delete flows in advisor/frontend/src/components/__tests__/Playbook.test.tsx

**Checkpoint**: Playbook page is live with seed data, tag filtering, and CRUD. Playbook entries appear in advisor chat context (handled by T016/T017 which load ALL pinned notes regardless of target_type).

---

## Phase 5: User Story 3 — Record and Reference Service Notes (Priority: P3)

**Goal**: Admin can add notes to services alongside the existing health history view. Advisor references service notes in chat.

**Independent Test**: Create a service note, start a fresh chat, ask about that service — advisor references the note.

### Implementation for User Story 3

- [x] T024 [US3] Add notes tab to ServiceDetailModal alongside existing health history, showing NotesList component (target_type='service', target_id=service_definition.id) in advisor/frontend/src/components/ServiceDetailModal.tsx

### Tests for User Story 3

- [x] T025 [US3] Write Vitest component test for ServiceDetailModal notes tab: renders notes, add/edit/delete flows in advisor/frontend/src/components/__tests__/ServiceDetailModal.test.tsx

**Checkpoint**: Service notes are functional. Admin can annotate services and the advisor references them in chat. All three note categories (device, playbook, service) are now complete.

---

## Phase 6: User Story 4 — LLM-Suggested Notes with Approval (Priority: P4)

**Goal**: "Suggest notes" button in chat triggers an LLM call to extract facts from the conversation. Admin reviews, approves, edits, or rejects suggestions. Rejections are remembered.

**Independent Test**: Have a chat mentioning network facts, click "Suggest notes", verify suggestions appear, approve one (creates a real note), reject one (doesn't reappear).

### Implementation for User Story 4

- [x] T026 [P] [US4] Create note_suggester service with generate_suggestions() function: assembles a focused extraction prompt, calls Ollama via existing stream_chat() (collected non-streaming), parses JSON response, filters out rejected hashes, returns 0–3 suggestions in advisor/backend/app/services/note_suggester.py
- [x] T027 [US4] Add POST /api/chat/conversations/{id}/suggest-notes endpoint to chat router: loads conversation messages, calls note_suggester, returns suggestions (empty list + error field if Ollama unreachable) in advisor/backend/app/routers/chat.py
- [x] T028 [P] [US4] Create NoteSuggestionPanel component (review panel showing each suggestion with target label, body preview, and Approve/Edit/Reject buttons) in advisor/frontend/src/components/NoteSuggestionPanel.tsx
- [x] T029 [US4] Add "Suggest notes" button to ChatComposer (visible when conversation has messages, disabled during streaming) in advisor/frontend/src/components/ChatComposer.tsx
- [x] T030 [US4] Integrate NoteSuggestionPanel into Chat page: show panel when suggestions are loaded, handle approve (POST /api/notes), edit (open PlaybookModal/NotesList pre-filled), reject (POST /api/notes/rejected-suggestions) in advisor/frontend/src/pages/Chat.tsx

### Tests for User Story 4

- [x] T031 [P] [US4] Write pytest tests for note_suggester: valid JSON extraction, empty conversation returns [], Ollama unreachable returns empty gracefully, rejected hashes filtered out in advisor/backend/tests/test_note_suggester.py
- [x] T032 [P] [US4] Write pytest test for suggest-notes endpoint: returns suggestions, returns empty on Ollama failure, 404 on missing conversation in advisor/backend/tests/test_suggest_notes.py

**Checkpoint**: Full suggestion workflow functional. Admin can trigger suggestions, approve/edit/reject them. Rejected suggestions don't resurface.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validation, backup verification (US5), and final cleanup.

- [x] T033 Verify notes tables are included in standard pg_dump backup path (US5 — no separate backup step needed, just verify tables exist in same database)
- [x] T034 Run quickstart.md validation steps end-to-end (all 10 steps) to confirm feature works on deployed advisor, including a timing check for SC-007: measure advisor response time with 50 pinned notes vs 0 and verify ≤10% degradation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately. T001–T005 are parallel; T006 depends on T001+T002 (models must exist for migration); T007 depends on T001+T002 (parallel with T006)
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories. T008–T010 are sequential (same file). T012+T013 are parallel with each other and with T008–T011
- **User Stories (Phase 3–6)**: All depend on Phase 2 completion. Can proceed sequentially in priority order (P1 → P2 → P3 → P4)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2. No dependencies on other stories. **This is the MVP.**
- **US2 (P2)**: Can start after Phase 2. Independent of US1 (prompt assembler already loads all note types from T016/T017). Reuses NotesList from US1 indirectly (PlaybookModal is a separate component since playbook entries have title+tags).
- **US3 (P3)**: Can start after Phase 2. Reuses NotesList component from T014. Independent of US1/US2.
- **US4 (P4)**: Can start after Phase 2. Depends on notes CRUD being functional (Phase 2). Frontend integration in T030 may reference PlaybookModal from US2 for the "edit" flow, but can fall back to a simple inline editor if US2 is not yet complete.
- **US5 (P5)**: Verified in Polish phase. No implementation needed — backup coverage is automatic.

### Within Each User Story

- Models → Services → Endpoints → Frontend (sequential within story)
- Tests come AFTER implementation (Constitution Principle IV: Test-After)
- Tasks marked [P] within a story can run in parallel

### Parallel Opportunities

- **Phase 1**: T001, T002, T003, T004, T005 are all parallel (different files)
- **Phase 2**: T012 + T013 are parallel (different existing router files)
- **Phase 3 (US1)**: T014 is parallel with T016/T017 (frontend vs backend). T018 + T019 are parallel (different test files)
- **Phase 4 (US2)**: T020 is parallel with other US2 tasks initially (independent component)
- **Phase 6 (US4)**: T026 parallel with T028 (backend service vs frontend component). T031 + T032 are parallel

---

## Parallel Example: Phase 1 Setup

```text
# All model + schema + type tasks can run in parallel:
T001: Create Note model in advisor/backend/app/models/note.py
T002: Create RejectedSuggestion model in advisor/backend/app/models/rejected_suggestion.py
T003: Create Pydantic schemas in advisor/backend/app/schemas/note.py
T004: Add TypeScript types in advisor/frontend/src/types.ts
T005: Create notes API service in advisor/frontend/src/services/notes.ts

# Then sequentially:
T006: Create migration (depends on T001, T002)
T007: Import models in env.py (depends on T001, T002)
```

## Parallel Example: User Story 1 (MVP)

```text
# Backend and frontend can start in parallel:
T014: Create NotesList component (frontend)
T016: Add _load_notes_section() to prompt_assembler (backend)

# Then sequential integration:
T015: Add notes to DeviceAnnotationModal (depends on T014)
T017: Update SYSTEM_PREAMBLE + wire notes section (depends on T016)

# Tests after implementation (parallel):
T018: pytest notes CRUD tests
T019: pytest prompt assembler notes tests
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (models, migration, schemas, types, API service)
2. Complete Phase 2: Foundational (CRUD router, cascade deletes)
3. Complete Phase 3: User Story 1 (device notes + advisor grounding)
4. **STOP and VALIDATE**: Create a device note, start a chat, ask about the device — advisor references the note with attribution
5. Deploy via `bash scripts/deploy-advisor.sh` if ready

### Incremental Delivery

1. Setup + Foundational → Notes API is live, seed playbook data queryable
2. Add US1 (Device Notes + Grounding) → MVP! Test independently → Deploy
3. Add US2 (Playbook Page) → Tag filtering + dedicated page → Deploy
4. Add US3 (Service Notes) → Complete note coverage → Deploy
5. Add US4 (LLM Suggestions) → Enhancement layer → Deploy
6. Polish → Quickstart validation → Final deploy

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable after Phase 2
- Tests come AFTER implementation (Constitution Principle IV: Test-After)
- Commit after each task or logical group
- Stop at any checkpoint to validate the story independently
- Deploy path: `bash scripts/deploy-advisor.sh` (rsync+SSH to HOLYGRAIL)
