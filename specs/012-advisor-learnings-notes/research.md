# Research: Advisor Learnings & Curated Notes

**Branch**: `012-advisor-learnings-notes` | **Date**: 2026-04-12

## R-001: Polymorphic vs Dedicated Notes Tables

**Decision**: Single polymorphic `notes` table with `target_type` + `target_id` columns.

**Rationale**: The alerts model (migration 004) already uses this exact pattern — `target_type` (String(20)) and `target_id` (int, nullable) — to reference devices, services, or system-level targets from a single table. Following this established project pattern keeps the codebase consistent. A single table also simplifies the prompt assembler's query: one `SELECT` loads all notes for the grounding context, rather than three separate queries joined together.

**Alternatives considered**:
- **Dedicated tables** (`device_notes`, `service_notes`, `playbook_entries`): Allows proper FK constraints with CASCADE delete. Rejected because it triples the migration, model, and CRUD boilerplate for no meaningful safety gain in a single-admin system, and complicates the prompt assembler query.
- **Extending the existing `annotations` table**: The annotations table is 1:1 with devices and has a fixed schema (role, description, tags). Notes are 1:many and apply to multiple target types. Extending annotations would distort its purpose.

**Cascade delete handling**: Since a polymorphic FK can't reference multiple parent tables, cascade delete for orphaned notes will be handled at the application level — the device and service deletion code paths will include a cleanup step that deletes associated notes. This matches the project's existing patterns where alerts also lack FK cascades.

## R-002: Playbook Entries — Separate Entity or Note Subtype

**Decision**: Playbook entries are rows in the same `notes` table with `target_type = 'playbook'` and `target_id = NULL`. The `title` and `tags` columns are nullable on the table and populated only for playbook entries.

**Rationale**: Playbook entries differ from device/service notes only by having a `title` and `tags`. Adding two nullable columns to the notes table is simpler than creating a separate table with its own CRUD routes, model, and frontend service layer. The advisor's prompt assembler loads all notes in one query regardless.

**Alternatives considered**:
- **Separate `playbook_entries` table**: Clean separation but doubles the API surface for no functional benefit. The UI and API can distinguish by `target_type`.

## R-003: Tag Storage and Autocomplete

**Decision**: Tags stored as a JSON array column on the `notes` table (same pattern as `annotations.tags`). Autocomplete served by a dedicated endpoint that queries `SELECT DISTINCT unnest(tags)` from playbook notes.

**Rationale**: The annotations model already stores tags as `JSON` with `server_default="[]"`. Reusing this pattern is consistent and avoids a separate tags table. PostgreSQL's `jsonb_array_elements_text()` function efficiently extracts unique tags for autocomplete.

**Alternatives considered**:
- **Separate `tags` table with M:N join**: Normalised but over-engineered for ~50 entries with free-form tags in a single-admin system.
- **Comma-separated string**: Harder to query and filter than JSON array.

## R-004: Note Suggestions — Transient vs Persisted

**Decision**: Suggestions are transient. The "Suggest notes" button triggers a single LLM call that returns 0–3 suggestions in the HTTP response body. Suggestions live only in the frontend state until the admin acts. Approved suggestions become normal notes via `POST /api/notes`. Rejected suggestions are recorded in a `rejected_suggestions` table (content hash only) to prevent re-surfacing.

**Rationale**: Suggestions have no lifecycle beyond the review panel. Persisting them in a suggestions table would add complexity (status tracking, cleanup) with no benefit. The only thing worth persisting is the rejection signal, which is a single hash row.

**Alternatives considered**:
- **Persisted suggestions table with status**: Adds a full CRUD layer for an ephemeral concept. Rejected because suggestions don't need to survive page refreshes — the admin either acts on them immediately or dismisses them.

## R-005: Prompt Assembler Integration Pattern

**Decision**: Add a new `_load_notes_section()` function in `prompt_assembler.py` following the existing `_load_devices_section()` / `_load_services_section()` pattern. Wrap it in `_safe_load()` for graceful degradation. Insert the "## Admin Notes" section after "## Active Alerts" and before "## Recent events" in the system prompt.

**Rationale**: The prompt assembler already has a clean pattern: each section has a dedicated loader function, each wrapped in `_safe_load()` which catches exceptions and returns a placeholder. The notes section follows this pattern exactly. Placing notes after alerts and before events puts durable context (notes) near the alert context it's most likely to complement, while keeping the volatile event log last.

**Section format**: Each note in the prompt will be labeled with its source for attribution:
```
## Admin Notes

### Device: NAS (192.168.10.105)
- [pinned] Goes offline Sunday 2 AM–3 AM for RAID scrub — not a real outage

### Playbook: VPN Rotation Schedule
- VPN credentials rotate on the first Monday of every month. Contact info in 1Password.
```

**Budget handling**: Pinned notes are always included. Unpinned notes are appended only if `total_chars < MAX_PROMPT_CHARS`. The existing trimming loop (which removes oldest conversation messages first) remains unchanged — if notes push the prompt over budget, conversation history is trimmed, not notes. This matches FR-012.

## R-006: LLM Suggestion Prompt Design

**Decision**: The suggestion call uses the existing `stream_chat()` Ollama client (consumed non-streaming by collecting all chunks) with a focused system prompt instructing the model to extract 0–3 durable facts from the conversation. Response is parsed as JSON.

**Rationale**: Reuses the existing Ollama client infrastructure (`ollama_client.py`). The model is already `llama3.1:8b`. A non-streaming consumption pattern (collect all chunks into a string, then JSON-parse) is the simplest approach for a single-shot extraction call.

**Suggestion prompt template**:
```
You are analyzing a conversation between a network admin and their advisor.
Extract 0–3 facts about the admin's network that would be worth saving as
durable notes. Only extract facts the admin explicitly stated — do not infer
or speculate. Return a JSON array of objects:
[{"target_type": "device"|"service"|"playbook", "target_id": <int or null>,
  "target_label": "<name>", "body": "<note text>"}]
Return [] if nothing is worth saving.
```

**Deduplication**: Before presenting suggestions, the backend hashes each suggestion body (SHA-256 of lowercased, whitespace-normalised text) and filters out any that match entries in `rejected_suggestions`.

## R-007: Pinned Notes Cap Enforcement

**Decision**: Enforce the 20-pinned-per-category cap at the API level. When the admin attempts to pin a note that would exceed the limit, the API returns a 409 Conflict with a descriptive message. The frontend displays this as an inline warning.

**Rationale**: Enforcing at the API level (rather than database constraint) keeps the logic simple and the error message user-friendly. A database CHECK constraint on a count aggregate isn't straightforward in PostgreSQL.

**Alternatives considered**:
- **Database trigger**: More robust but harder to maintain and debug in this project's simplicity-first approach.
- **Frontend-only enforcement**: Racey and bypassable. API enforcement is the correct boundary.
