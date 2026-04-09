# Implementation Plan: Ollama LLM Deployment with GPU Acceleration

**Branch**: `006-ollama-gpu-deployment` | **Date**: 2026-04-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-ollama-gpu-deployment/spec.md`

## Summary

Deploy Ollama as a GPU-accelerated LLM inference server on HOLYGRAIL with the RTX 2070 Super, pull Llama 3.1 8B as the default model, expose an OpenAI-compatible API on the LAN via Traefik hostname routing, and benchmark baseline performance. This establishes the AI backbone for Phase 4+ features (Network Advisor, alert summarization, log triage).

## Technical Context

**Language/Version**: Bash (POSIX shell scripts), Docker Compose YAML  
**Primary Dependencies**: Docker Compose v2, Ollama (latest), nvidia-container-toolkit, Traefik (existing)  
**Storage**: Docker volume for model persistence (ollama_data)  
**Testing**: Manual verification + benchmark script (test-after per Constitution IV)  
**Target Platform**: HOLYGRAIL (Ubuntu 24.04 LTS, x86_64, RTX 2070 Super 8GB)  
**Project Type**: Infrastructure/DevOps (Docker Compose deployment)  
**Performance Goals**: >=10 tokens/sec generation, <10s response for short prompts  
**Constraints**: 8 GB VRAM budget, LAN-only access, model must fit entirely in GPU memory  
**Scale/Scope**: Single admin, 1 container, 1 default model, single-user inference

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --- | --- | --- |
| I. Local-First | PASS | LLM runs entirely on LAN. No cloud APIs. Model download is one-time; operates offline after. Constitution explicitly states "Ollama provides LLM inference locally." |
| II. Simplicity & Pragmatism | PASS | Single Docker container, single compose file, shell script for benchmark. Official Ollama image handles everything. No custom inference code. |
| III. Containerized Everything | PASS | Ollama in Docker with NVIDIA runtime. Own compose file per constitution. `restart: unless-stopped`. Secrets via `.env` (none needed — no auth). |
| IV. Test-After | PASS | Benchmark script and verification run after deployment, not before. |
| V. Observability | PASS | Health endpoint at `/` ("Ollama is running"). Docker healthcheck configured. Constitution tech stack lists Ollama as both "LLM inference" and "monitoring intelligence layer." |

**Post-Phase 1 Re-check**: All gates still pass.

## Project Structure

### Documentation (this feature)

```text
specs/006-ollama-gpu-deployment/
├── plan.md              # This file
├── research.md          # Phase 0 output — 8 research decisions
├── data-model.md        # Phase 1 output — config entities, API contract, benchmark format
├── quickstart.md        # Phase 1 output — deployment steps and verification
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
infrastructure/holygrail/
├── ollama/
│   ├── docker-compose.yml   # NEW — Ollama with NVIDIA runtime + Traefik labels
│   └── .env.example         # NEW — operational config (no secrets)
├── traefik/
│   └── (no changes — Docker labels auto-discovered)
├── monitoring/
│   └── (no changes)
├── plex/
│   └── (no changes)
└── docker/
    └── (no changes)

scripts/
├── benchmark-ollama.sh      # NEW — performance baseline measurement
└── setup-holygrail-dns.sh   # MODIFIED — add ollama.holygrail entry

docs/
└── INFRASTRUCTURE.md         # MODIFIED — add Ollama service, hostname, benchmark results
```

**Structure Decision**: Single compose file in `infrastructure/holygrail/ollama/` per Constitution III. Joins existing `holygrail-proxy` external network for Traefik routing. Benchmark script in `scripts/` alongside existing infrastructure scripts.

## Complexity Tracking

> No constitution violations. No justifications needed.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --- | --- | --- |
| (none) | — | — |
