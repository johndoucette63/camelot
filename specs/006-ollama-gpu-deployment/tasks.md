# Tasks: Ollama LLM Deployment with GPU Acceleration

**Input**: Design documents from `/specs/006-ollama-gpu-deployment/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Not requested. Benchmark script (US4) serves as post-deployment validation per Constitution IV (Test-After).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory structure and environment template

- [x] T001 Create directory structure: `infrastructure/holygrail/ollama/`
- [x] T002 [P] Create Ollama `.env.example` with `OLLAMA_HOST` (default: 0.0.0.0), `OLLAMA_MODELS` (default: /root/.ollama), and `TZ` variables in `infrastructure/holygrail/ollama/.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational tasks needed — Ollama is self-contained. The `holygrail-proxy` network and Traefik already exist from F2.2.

**Checkpoint**: Proceed directly to US1.

---

## Phase 3: User Story 1 - Deploy GPU-Accelerated LLM Server (Priority: P1) MVP

**Goal**: Ollama running in Docker with NVIDIA GPU passthrough on HOLYGRAIL. Server starts, GPU is visible inside container, auto-restarts on reboot.

**Independent Test**: `ssh john@holygrail "curl -s http://localhost:11434/"` returns "Ollama is running" and `nvidia-smi` inside the container shows the RTX 2070 Super.

### Implementation for User Story 1

- [x] T003 [US1] Create Ollama `docker-compose.yml` with NVIDIA runtime, GPU passthrough (`deploy.resources.reservations.devices`), `holygrail-proxy` external network, persistent `ollama_data` volume, `restart: unless-stopped`, port 11434, `OLLAMA_HOST=0.0.0.0` environment variable, and Docker healthcheck (`curl -f http://localhost:11434/`) in `infrastructure/holygrail/ollama/docker-compose.yml`

**Checkpoint**: Ollama container deployable on HOLYGRAIL. Server responds on port 11434. GPU visible inside container. This is the MVP.

---

## Phase 4: User Story 2 - Pull and Serve Default Model (Priority: P2)

**Goal**: Llama 3.1 8B downloaded and ready to serve. Model fits in VRAM, responds coherently to prompts.

**Independent Test**: `curl http://192.168.10.129:11434/api/generate -d '{"model":"llama3.1:8b","prompt":"Hello"}'` returns a streamed response.

### Implementation for User Story 2

- [x] T004 [US2] Create a model pull helper script that runs `docker exec ollama ollama pull llama3.1:8b` and verifies the model appears in `ollama list` in `scripts/setup-ollama-model.sh`

**Checkpoint**: Model is pulled, persisted in volume, and responds to prompts. GPU memory usage confirmed within 8 GB budget.

---

## Phase 5: User Story 3 - Expose LAN-Accessible AI API (Priority: P3)

**Goal**: OpenAI-compatible API accessible from any LAN device via `ollama.holygrail` hostname and direct port 11434. Firewall configured.

**Independent Test**: From Mac, `curl http://ollama.holygrail/v1/chat/completions -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Hi"}]}'` returns a valid chat completions response.

### Implementation for User Story 3

- [x] T005 [US3] Add Traefik Docker labels for `ollama.holygrail` hostname routing to the Ollama service (entrypoint: web, port: 11434) in `infrastructure/holygrail/ollama/docker-compose.yml`. Labels: `traefik.enable=true`, `traefik.http.routers.ollama.rule=Host('ollama.holygrail')`, `traefik.http.routers.ollama.entrypoints=web`, `traefik.http.services.ollama.loadbalancer.server.port=11434`
- [x] T006 [P] [US3] Update Mac DNS setup script to add `ollama.holygrail` entry in `scripts/setup-holygrail-dns.sh`. Add "ollama.holygrail" to the HOSTNAMES array.
- [x] T007 [US3] Document UFW firewall command to allow port 11434 from LAN in the Ollama compose file header comment: `sudo ufw allow from 192.168.10.0/24 to any port 11434 comment 'Ollama LLM API'`

**Checkpoint**: Chat completions API accessible from Mac via both `ollama.holygrail` and `192.168.10.129:11434`. Firewall allows LAN access only.

---

## Phase 6: User Story 4 - Benchmark and Document Performance (Priority: P4)

**Goal**: Documented tokens/sec, latency, and VRAM numbers for Llama 3.1 8B on RTX 2070 Super.

**Independent Test**: Run `bash scripts/benchmark-ollama.sh` and verify it outputs prompt eval rate, generation rate, latency for 3 prompt sizes, and VRAM usage.

### Implementation for User Story 4

- [x] T008 [US4] Create benchmark script that sends prompts of 3 sizes (short ~20 words, medium ~200 words, advisor-length ~500 words) to the Ollama `/api/generate` endpoint, parses `eval_count`/`eval_duration` from the streaming response, measures wall-clock latency, and reports VRAM usage via `nvidia-smi` in `scripts/benchmark-ollama.sh`
- [x] T009 [US4] Update INFRASTRUCTURE.md: add Ollama to HOLYGRAIL deployed services table (port 11434), add `ollama.holygrail` to hostname table, add benchmark results section with placeholders for tokens/sec, latency, and VRAM in `docs/INFRASTRUCTURE.md`

**Checkpoint**: Benchmark script produces reproducible metrics. Results documented in repo.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation updates

- [x] T010 [P] Update CLAUDE.md recent changes section with Ollama deployment summary in `CLAUDE.md`
- [x] T011 Run quickstart.md end-to-end validation: follow all deployment steps on HOLYGRAIL and verify each checkpoint passes
- [x] T012 Review Ollama compose file for consistency with other HOLYGRAIL stacks: verify `restart: unless-stopped`, healthcheck, `holygrail-proxy` network, no hardcoded credentials

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **US1 (Phase 3)**: Depends on Setup — core container deployment
- **US2 (Phase 4)**: Depends on US1 — needs running Ollama to pull model
- **US3 (Phase 5)**: Depends on US1 — needs running Ollama for Traefik routing; can run in parallel with US2
- **US4 (Phase 6)**: Depends on US1 and US2 — needs model loaded for benchmarking
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Setup — this is the MVP
- **User Story 2 (P2)**: Depends on US1 — model pull requires running server
- **User Story 3 (P3)**: Depends on US1 — can run in parallel with US2 (Traefik labels don't need a model loaded)
- **User Story 4 (P4)**: Depends on US1 + US2 — benchmarking requires a loaded model

### Parallel Opportunities

- T001 and T002 can run in parallel (setup phase, different files)
- US2 (T004) and US3 (T005-T007) can run in parallel after US1 completes
- T005 and T006 can run in parallel within US3 (different files)
- T010, T011, T012 — T010 can run in parallel with T011/T012

---

## Parallel Example: User Story 3

```bash
# After US1 (T003) is complete, launch in parallel:
Task: "Add Traefik labels to Ollama compose in infrastructure/holygrail/ollama/docker-compose.yml"
Task: "Update DNS setup script in scripts/setup-holygrail-dns.sh"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 3: User Story 1 (T003)
3. **STOP and VALIDATE**: Deploy on HOLYGRAIL, verify GPU passthrough, confirm server responds
4. Ollama is running with GPU — this alone provides the LLM backbone

### Incremental Delivery

1. Complete Setup → directory ready
2. Add US1 → Deploy Ollama container → Validate GPU (MVP!)
3. Add US2 → Pull Llama 3.1 8B → Validate inference works
4. Add US3 → Traefik routing + firewall → Validate LAN access
5. Add US4 → Run benchmarks → Document baseline
6. Each story adds value without breaking previous stories

### Single Developer Strategy (Camelot)

Since this is a single-admin project:
1. Work sequentially: Setup → US1 → US2 → US3 → US4 → Polish
2. US2 and US3 can be batched after US1 since they touch different files
3. Deploy and verify at each checkpoint

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- This is a simpler feature than F2.2 — single container, no multi-service compose
- Model pull (US2) requires internet access (one-time download ~4.5 GB)
- Traefik labels on the Ollama compose are included in T005 as a separate task from T003 to keep US1 (MVP) independent of Traefik
- Commit after each task or logical group
