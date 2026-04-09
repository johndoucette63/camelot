# Research: Ollama LLM Deployment with GPU Acceleration

**Feature Branch**: `006-ollama-gpu-deployment`  
**Date**: 2026-04-08

## R-001: Ollama Docker Image and GPU Passthrough

**Decision**: Use the official `ollama/ollama` Docker image with NVIDIA runtime.

**Rationale**: Ollama provides an official Docker image that supports GPU passthrough via `--gpus all` or the NVIDIA container runtime. HOLYGRAIL already has nvidia-container-toolkit installed (Phase 1). The official image handles GPU detection, model management, and the API server in a single container.

**Alternatives considered**:
- Manual install on host — rejected, violates Constitution III (Containerized Everything).
- vLLM or llama.cpp server — rejected, Ollama provides the simplest deployment with built-in model management and OpenAI-compatible API. Constitution II (simplest thing that works).

## R-002: Default Model Selection

**Decision**: Llama 3.1 8B (quantized, Q4_K_M or similar) as the default model.

**Rationale**: Llama 3.1 8B is the best general-purpose model that fits comfortably within 8 GB VRAM. The 4-bit quantized version uses approximately 4.5-5 GB VRAM, leaving headroom for KV cache during inference. Strong at instruction following, conversation, and text analysis — all needed for the Network Advisor use cases (alert summarization, anomaly explanation, log triage).

**Alternatives considered**:
- Llama 3.1 70B — rejected, requires 40+ GB VRAM, far exceeds RTX 2070S capacity.
- Mistral 7B — viable alternative, slightly less capable at instruction following than Llama 3.1 8B. Good fallback if Llama 3.1 8B proves too slow.
- Phi-3 Mini (3.8B) — rejected as default, too small for complex advisory prompts. Could be a fast secondary model.

## R-003: Compose Organization (Constitution III)

**Decision**: Separate Docker Compose file at `infrastructure/holygrail/ollama/docker-compose.yml`, per-stack as established in F2.2.

**Rationale**: Constitution III states "Each service stack gets its own docker-compose.yml." Ollama is a distinct service stack from monitoring and Traefik. Uses the shared `holygrail-proxy` external network for Traefik routing.

**Alternatives considered**:
- Add to monitoring compose — rejected, LLM inference is a separate concern from network monitoring.
- Add to a new "AI stack" compose — rejected, YAGNI. Ollama is the only AI service for now.

## R-004: Traefik Integration

**Decision**: Use Docker labels for Traefik routing (`ollama.holygrail` → port 11434).

**Rationale**: Ollama runs in bridge network mode (unlike Plex which uses host mode), so Docker labels work natively with Traefik's Docker provider. No file-provider entry needed.

**Alternatives considered**:
- File provider route — rejected, unnecessary since Ollama uses bridge networking.
- No Traefik routing — rejected, spec FR-006 requires hostname access.

## R-005: UFW Firewall Configuration

**Decision**: Add UFW rule allowing port 11434 from 192.168.10.0/24 only.

**Rationale**: Spec FR-007 requires LAN-only access. Consistent with existing UFW rules for Portainer (9443) and Plex (32400). Single rule: `ufw allow from 192.168.10.0/24 to any port 11434`.

**Alternatives considered**:
- No firewall rule (rely on Docker networking) — rejected, defense in depth. Existing services all have explicit UFW rules.

## R-006: Secrets Management

**Decision**: Minimal `.env.example` for Ollama — no secrets required.

**Rationale**: Ollama has no built-in authentication (LAN-only per Constitution I). The only configurable values are operational (model name, VRAM limits, host binding). No passwords or API keys needed.

## R-007: Benchmark Script Approach

**Decision**: Shell script using Ollama's built-in `/api/generate` endpoint with timing.

**Rationale**: Constitution II (simplest thing that works). A bash script with `curl` and `time` can measure tokens/sec by parsing Ollama's streaming response (which includes eval_count and eval_duration). No Python dependencies needed for the benchmark itself.

**Alternatives considered**:
- Python benchmark script — rejected, adds unnecessary dependency for what `curl` + `jq` can do.
- llm-benchmark suite — rejected, overkill for a single-model baseline measurement.

## R-008: Health Endpoint (Constitution V)

**Decision**: Use Ollama's built-in health endpoint at `/` (returns "Ollama is running") as the Docker healthcheck.

**Rationale**: Constitution V requires all services to expose a /health endpoint. Ollama's root endpoint serves this purpose — it returns a 200 response when the server is ready. Docker healthcheck configured as `curl -f http://localhost:11434/`.
