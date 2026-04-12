# Implementation Plan: Advisor Learnings & Curated Notes

**Branch**: `012-advisor-learnings-notes` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/012-advisor-learnings-notes/spec.md`

## Summary

Add a user-curated notes and playbook layer to the Network Advisor. Notes attach to devices, services, or stand alone as cross-cutting playbook entries. The advisor chat's prompt assembler includes notes in its grounding context so the admin doesn't have to re-explain network context in every conversation. An optional "Suggest notes" button uses the existing Ollama LLM to propose notes from conversation content, with full admin approval before anything is saved.

The implementation uses a single polymorphic `notes` table (matching the existing alerts `target_type`/`target_id` pattern), extends `prompt_assembler.py` with a new notes section, adds CRUD endpoints and a frontend Playbook page, and integrates notes into the existing device/service detail modals.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 (frontend)
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14, httpx 0.28; React 18, Vite 6, Tailwind CSS 3, react-router-dom 7, TanStack React Table 8, react-markdown 10
**Storage**: PostgreSQL 16 in existing `advisor_pgdata` Docker volume, extended via Alembic migration `005_advisor_notes.py`
**Testing**: pytest (backend), Vitest + React Testing Library (frontend)
**Target Platform**: Linux server (HOLYGRAIL x86_64) + browser frontend
**Project Type**: Web service (FastAPI + React SPA)
**Performance Goals**: Notes loading adds <100ms to prompt assembly; total pinned notes context stays within existing 60,000 char budget
**Constraints**: Single-admin, local-only, Ollama for LLM (graceful degradation if unavailable)
**Scale/Scope**: ~50 notes expected; 20 pinned cap per category; 2KB max per note body

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --- | --- | --- |
| I. Local-First | **PASS** | All data stays in local PostgreSQL. LLM calls go to local Ollama only. No cloud APIs. |
| II. Simplicity & Pragmatism | **PASS** | Single polymorphic table, plain fetch() API client, no new libraries. Follows existing patterns (alerts target_type/target_id, annotations tags JSON). |
| III. Containerized Everything | **PASS** | No new containers. Extends existing advisor backend/frontend/db stack. |
| IV. Test-After | **PASS** | Implementation first, tests after. pytest for backend, Vitest for frontend. |
| V. Observability | **PASS** | Notes section gracefully degrades (FR-013). Suggestion failures logged and silently skipped (FR-019). Health endpoint unaffected. |
| Prohibited Tech | **PASS** | No new prohibited technologies. No GraphQL, no K8s, no cloud services. |

**Post-Phase 1 Re-check**: No violations. Design stays within existing stack and patterns.

## Project Structure

### Documentation (this feature)

```text
specs/012-advisor-learnings-notes/
├── plan.md              # This file
├── research.md          # Phase 0 output — design decisions
├── data-model.md        # Phase 1 output — entity definitions
├── quickstart.md        # Phase 1 output — verification steps
├── contracts/
│   └── api.md           # Phase 1 output — REST API contracts
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
advisor/
├── backend/
���   ├── app/
│   │   ├── models/
│   │   │   ├── note.py                    # NEW — Note SQLAlchemy model
│   │   │   └── rejected_suggestion.py     # NEW — RejectedSuggestion model
��   │   ├── routers/
│   │   │   ├── notes.py                   # NEW — Notes CRUD endpoints
│   │   │   └── chat.py                    # MODIFIED — add suggest-notes endpoint
│   │   ├── services/
│   │   │   ├── prompt_assembler.py        # MODIFIED — add _load_notes_section()
│   │   │   ├── note_suggester.py          # NEW — LLM suggestion logic
│   │   │   └── ollama_client.py           # UNCHANGED (reused for suggestions)
│   │   ├── schemas/
│   │   │   └── note.py                    # NEW — Pydantic request/response schemas
│   │   └── main.py                        # MODIFIED — register notes router
│   ├── migrations/
│   │   └── versions/
│   │       └── 005_advisor_notes.py       # NEW — migration for notes + rejected_suggestions
│   └── tests/
│       ├── test_notes_api.py              # NEW — notes CRUD tests
│       ├── test_note_suggester.py         # NEW — suggestion logic tests
│       └── test_prompt_assembler.py       # MODIFIED — test notes section assembly
├── frontend/
│   └── src/
│       ├── pages/
│       │   └── Playbook.tsx               # NEW — Playbook page
│       ├── components/
│       │   ├��─ PlaybookModal.tsx           # NEW — create/edit playbook entries
│       │   ├── NotesList.tsx              # NEW — reusable notes list + add/edit/delete
│       │   ├── NoteSuggestionPanel.tsx    # NEW — suggestion review panel
│       │   ├── DeviceAnnotationModal.tsx  # MODIFIED — add notes tab
│       │   ├── ServiceDetailModal.tsx     # MODIFIED — add notes tab
���       │   └── ChatComposer.tsx           # MODIFIED — add "Suggest notes" button
│       ├── services/
│       │   └── notes.ts                   # NEW — notes API client
│       ├── App.tsx                        # MODIFIED — add Playbook route + nav entry
│       └── types.ts                       # MODIFIED — add Note, Suggestion types
```

**Structure Decision**: Follows the existing advisor app structure. New files follow the established pattern: models in `models/`, routers in `routers/`, business logic in `services/`, Pydantic schemas in `schemas/`. Frontend follows the existing pages/components/services split. No new directories needed beyond `schemas/` (which may already exist or can be a single file in `routers/`).

## Complexity Tracking

> No constitution violations. Table left empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| —         | —          | —                                    |
