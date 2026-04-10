# Implementation Plan: AI-Powered Advisor Chat

**Branch**: `010-ai-advisor-chat` | **Date**: 2026-04-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/Users/jd/Code/camelot/specs/010-ai-advisor-chat/spec.md`

## Summary

Add a conversational chat interface to the existing advisor web app (`advisor/`) that lets the single home admin ask natural-language questions about the network and get streamed, grounded answers from the local Ollama LLM on HOLYGRAIL. Grounding is limited to the data the advisor already owns: device inventory from F4.2 and services / service health / alerts / events from F4.3. Conversations and messages persist in the advisor's existing Postgres database via a new Alembic migration. The chat supports multi-turn memory, in-flight cancellation with partial-response save, and resume-on-reload with a "New chat" button.

Technical approach: extend the existing FastAPI backend with a new `chat` router that owns conversation/message CRUD, a prompt assembler that pulls from the existing F4.2/F4.3 data stores, and an Ollama streaming client built on the already-installed `httpx`. Stream tokens to the browser over a FastAPI `StreamingResponse` (newline-delimited JSON frames) and rely on `request.is_disconnected()` to detect client-initiated cancellation and abort the Ollama call. Add a React `Chat` page under `advisor/frontend/src/pages/`, wired into the existing `react-router-dom` tree alongside Home/Devices/Services/Events.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 (frontend)
**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14, `httpx` 0.28 (already in `requirements.txt`, used as the Ollama client), Pydantic v2; React 18, Vite 6, Tailwind 3, react-router-dom 7, TanStack React Table 8 (not needed for this feature but available)
**Storage**: PostgreSQL 16 in the existing `advisor_pgdata` Docker volume, extended via Alembic migration `003_chat_conversations.py` adding `conversations` and `messages` tables
**Testing**: pytest + pytest-asyncio + httpx AsyncClient (backend, existing pattern under `advisor/backend/tests/`); Vitest + @testing-library/react (frontend, existing pattern under `advisor/frontend/src/components/__tests__/`)
**Target Platform**: Docker Compose stack on HOLYGRAIL (Ubuntu 24.04, x86_64). Backend and frontend already containerized under `advisor/docker-compose.yml`. Ollama runs in a sibling Compose stack on the same host and is reachable at `http://ollama:11434` (container network) or `http://holygrail:11434` (host network).
**Project Type**: Web application (backend + frontend monorepo under `advisor/`)
**Performance Goals**: First-token latency ≤ 3 s (SC-001) under normal conditions with Llama 3.1 8B on the 2070S; backend unreachable failure surfaced in ≤ 5 s (SC-005). Single-admin traffic (<100 msgs/day), no concurrency concerns.
**Constraints**: Local-only — Ollama is the sole LLM backend, no external API calls (Constitution I). Single-admin deployment — no auth gate added in this feature (inherits the existing advisor app's LAN-trusted posture). Grounding sources for v1 are strictly F4.2 inventory + F4.3 services/health/alerts/events; time-series, logs, IoT, and capacity data are explicitly deferred (per Clarification Q1).
**Scale/Scope**: Single admin, small network (≤ 10 devices, ≤ 50 services in v1), conversations expected to stay well under Llama 3.1 8B's 128 K context window.

## Constitution Check

Evaluated against `.specify/memory/constitution.md` v1.1.0.

| Principle | Assessment |
| --- | --- |
| **I. Local-First** | ✅ PASS. All inference runs on the local Ollama instance on HOLYGRAIL. Prompts and responses never leave the LAN. No cloud APIs, no telemetry. |
| **II. Simplicity & Pragmatism** | ✅ PASS. Reuses the existing `advisor/` monorepo, Postgres instance, Alembic migration pattern, and httpx dependency. Adds exactly two tables, one backend router, one frontend page, one Ollama client module. No new infra, no new services, no new languages, no abstraction layers. |
| **III. Containerized Everything** | ✅ PASS. Deploys via the existing `advisor/docker-compose.yml` with no new containers. Ollama already runs as a container from F3.1. |
| **IV. Test-After (Not Test-First)** | ✅ PASS. Implementation comes first; tests are written afterward using the existing pytest + Vitest harnesses. Tasks will be ordered implementation-before-tests. |
| **V. Observability** | ✅ PASS. Reuses the existing structured JSON logger. The chat router will emit structured log lines for each question, advisor reply (length + duration), and Ollama error so operational issues are visible in Docker logs. The existing `/health` endpoint covers liveness. Grafana/InfluxDB dashboards are not required for v1 per the simplicity principle (usage is single-admin). |

**Result**: No violations. Proceeding with Phase 0 research.

## Project Structure

### Documentation (this feature)

```text
specs/010-ai-advisor-chat/
├── plan.md              # This file
├── spec.md              # Feature spec (already written, clarified)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── chat-api.md      # REST contract for /chat endpoints
└── checklists/
    └── requirements.md  # Spec quality checklist (already exists)
```

### Source Code (repository root)

```text
advisor/
├── backend/
│   ├── app/
│   │   ├── main.py                        # EDIT: register chat router
│   │   ├── config.py                      # EDIT: add OLLAMA_BASE_URL, OLLAMA_MODEL
│   │   ├── models/
│   │   │   ├── conversation.py            # NEW: Conversation SQLAlchemy model
│   │   │   └── message.py                 # NEW: Message SQLAlchemy model
│   │   ├── routers/
│   │   │   └── chat.py                    # NEW: /chat/* endpoints
│   │   └── services/
│   │       ├── ollama_client.py           # NEW: async streaming Ollama client (httpx)
│   │       └── prompt_assembler.py        # NEW: builds system prompt from F4.2/F4.3 data
│   ├── migrations/versions/
│   │   └── 003_chat_conversations.py      # NEW: Alembic migration
│   └── tests/
│       ├── test_chat_api.py               # NEW: chat endpoints + streaming
│       ├── test_ollama_client.py          # NEW: client unit (mocked httpx)
│       └── test_prompt_assembler.py       # NEW: prompt content assertions
└── frontend/
    └── src/
        ├── App.tsx                        # EDIT: add /chat route
        ├── pages/
        │   └── Chat.tsx                   # NEW: chat page
        ├── components/
        │   ├── ChatThread.tsx             # NEW: scrollable message list
        │   ├── ChatMessage.tsx            # NEW: one message bubble (user | advisor)
        │   ├── ChatComposer.tsx           # NEW: input + submit + stop button
        │   └── __tests__/
        │       └── ChatThread.test.tsx    # NEW: component tests
        ├── services/
        │   └── chat.ts                    # NEW: fetch wrapper for /chat/* + stream reader
        └── types.ts                       # EDIT: add ChatConversation, ChatMessage types
```

**Structure Decision**: This feature slots entirely into the existing `advisor/` monorepo. No new top-level directories, no new Compose stacks, no new infrastructure components. Backend additions follow the existing convention (`models/`, `routers/`, `services/`, `tests/` at the same level as source). Frontend additions follow the existing page + components + services layout used by Devices/Services/Events.

## Complexity Tracking

No constitution violations require justification. Table intentionally empty.
