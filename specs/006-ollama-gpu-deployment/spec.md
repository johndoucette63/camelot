# Feature Specification: Ollama LLM Deployment with GPU Acceleration

**Feature Branch**: `006-ollama-gpu-deployment`  
**Created**: 2026-04-08  
**Status**: Draft  
**Input**: User description: "Deploy Ollama LLM with GPU acceleration on HOLYGRAIL and expose OpenAI-compatible API on LAN"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deploy GPU-Accelerated LLM Server (Priority: P1)

As the Camelot admin, I need a local LLM inference server running on HOLYGRAIL with GPU acceleration so that AI features have a fast, private backbone that never sends data off the network.

**Why this priority**: Without the inference server running, no downstream AI feature (Network Advisor, alert summarization, log triage) can function. This is the foundation of the entire Phase 3+ AI pipeline.

**Independent Test**: Deploy the LLM server container on HOLYGRAIL and verify the GPU is being used for inference by running a test prompt and checking GPU utilization.

**Acceptance Scenarios**:

1. **Given** HOLYGRAIL has Docker and NVIDIA runtime installed, **When** the LLM server container is deployed, **Then** the server process starts and the GPU is visible inside the container.
2. **Given** the LLM server is running, **When** the admin checks GPU status from inside the container, **Then** the RTX 2070 Super appears with its full 8 GB VRAM available.
3. **Given** the LLM server is running, **When** the server is deployed with restart policies, **Then** it automatically recovers after a HOLYGRAIL reboot within 3 minutes.
4. **Given** the LLM server is running, **When** the admin sends a test prompt, **Then** GPU utilization increases during inference (confirming GPU is being used, not CPU).

---

### User Story 2 - Pull and Serve a Default LLM Model (Priority: P2)

As the Camelot admin, I want a capable default language model downloaded and ready to serve so that AI features have a model available immediately without manual configuration.

**Why this priority**: The server is useless without a model. This story makes the deployment functional — a model that fits within the 8 GB VRAM budget and responds intelligently to prompts.

**Independent Test**: Send a natural language prompt to the model and receive a coherent, contextually appropriate response.

**Acceptance Scenarios**:

1. **Given** the LLM server is running, **When** the admin pulls the default model, **Then** the download completes and the model is stored persistently (survives container restarts).
2. **Given** the model is pulled, **When** the admin sends a test prompt, **Then** the model responds with a coherent answer within 10 seconds for a short prompt.
3. **Given** the model is running inference, **When** the admin checks GPU memory usage, **Then** the model fits within 8 GB VRAM without falling back to CPU/RAM offloading.
4. **Given** the model is loaded, **When** the admin sends a multi-turn conversation, **Then** the model maintains context across turns.

---

### User Story 3 - Expose LAN-Accessible AI API (Priority: P3)

As the Camelot admin, I want the LLM API accessible from any device on the local network via an industry-standard chat completions endpoint so that the Mac, Pis, and future Network Advisor app can all use it without custom client code.

**Why this priority**: LAN accessibility turns the LLM from a server-local tool into a network-wide AI service. The OpenAI-compatible API format means any standard client library works out of the box.

**Independent Test**: From the Mac workstation, send a chat completions request to the HOLYGRAIL LLM endpoint and receive a valid response.

**Acceptance Scenarios**:

1. **Given** the LLM server is running on HOLYGRAIL, **When** the admin sends a chat completions request from the Mac, **Then** the response arrives in the standard chat completions format.
2. **Given** the LLM API is exposed on the LAN, **When** the admin hits the models endpoint, **Then** it returns the list of available models.
3. **Given** the LLM API is accessible, **When** the admin accesses it via the Traefik hostname, **Then** the request is routed correctly and responds.
4. **Given** the firewall is active on HOLYGRAIL, **When** the admin checks the UFW rules, **Then** the LLM API port is allowed from the LAN subnet only.

---

### User Story 4 - Benchmark and Document Performance Baseline (Priority: P4)

As the Camelot admin, I want documented performance numbers for the deployed model so that I have a baseline to compare against when tuning models, changing hardware, or evaluating whether the system meets Phase 4 requirements.

**Why this priority**: Lower priority because the system works without benchmarks, but critical for informed decisions about model selection for the Network Advisor and future AI features.

**Independent Test**: Run the benchmark script, verify it produces tokens/sec, latency, and VRAM numbers, and check the results are recorded in documentation.

**Acceptance Scenarios**:

1. **Given** the model is serving requests, **When** the admin runs the benchmark, **Then** it reports tokens per second for both prompt evaluation and text generation.
2. **Given** the benchmark has run, **When** the admin checks the results, **Then** response latency is measured for prompts of varying lengths (short, medium, advisor-length).
3. **Given** the benchmark is complete, **When** the admin reads the infrastructure documentation, **Then** VRAM usage, tokens/sec, and latency numbers are recorded with the model name and hardware context.

---

### Edge Cases

- What happens if the model is larger than available VRAM — does the server gracefully fall back to partial CPU offloading or reject the model?
- What happens if the LLM server receives concurrent requests — does it queue them, process in parallel, or reject extras?
- How does the system behave if the GPU driver crashes or becomes unavailable — does the container restart and recover?
- What happens if the persistent model storage volume runs out of disk space — is there a clear error or silent failure?
- What happens if a client sends a malformed request to the API — does the server return a useful error or crash?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy the LLM inference server as a containerized service on HOLYGRAIL with GPU passthrough to the RTX 2070 Super.
- **FR-002**: System MUST pull and store a default language model that fits within 8 GB VRAM, capable of general-purpose text generation and conversation.
- **FR-003**: System MUST persist downloaded models in a durable volume so they survive container restarts and redeployments.
- **FR-004**: System MUST expose an OpenAI-compatible chat completions API endpoint accessible from any device on the 192.168.10.0/24 LAN.
- **FR-005**: System MUST expose a models listing endpoint so clients can discover available models.
- **FR-006**: System MUST integrate with Traefik for hostname-based access (e.g., `ollama.holygrail`).
- **FR-007**: System MUST configure the HOLYGRAIL firewall to allow the LLM API port from the LAN subnet only.
- **FR-008**: System MUST ensure the LLM server automatically restarts after a HOLYGRAIL reboot.
- **FR-009**: System MUST include a benchmark script that measures tokens/sec (prompt eval + generation), response latency, and VRAM usage.
- **FR-010**: System MUST document benchmark results in the repository alongside hardware and model context.
- **FR-011**: System MUST update INFRASTRUCTURE.md to reflect the new LLM service, its port, and hostname.

### Key Entities

- **LLM Server**: The containerized inference engine running on HOLYGRAIL with GPU passthrough. Serves models via an HTTP API.
- **Language Model**: The default downloaded model (e.g., Llama 3.1 8B) that fits within the 8 GB VRAM budget. Stored persistently.
- **Chat Completions API**: The OpenAI-compatible HTTP endpoint that clients use to send prompts and receive responses. Industry-standard format.
- **Benchmark Results**: Documented performance numbers (tokens/sec, latency, VRAM) that serve as the baseline for future model and hardware decisions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The LLM server starts and is ready to serve requests within 2 minutes of container deployment.
- **SC-002**: The default model responds to a short prompt (under 50 words) within 10 seconds.
- **SC-003**: GPU utilization increases during inference, confirming hardware acceleration is active (not CPU fallback).
- **SC-004**: The LLM API is reachable from the Mac workstation via both direct port and Traefik hostname.
- **SC-005**: The default model fits entirely in VRAM with no CPU/RAM offloading during inference.
- **SC-006**: After a simulated HOLYGRAIL reboot, the LLM server recovers and serves requests within 3 minutes without manual intervention.
- **SC-007**: Benchmark results (tokens/sec, latency, VRAM) are recorded in repository documentation.
- **SC-008**: The system generates at least 10 tokens per second for text generation with the default model.

## Assumptions

- HOLYGRAIL has Docker Engine, Docker Compose v2, NVIDIA driver (570+), and nvidia-container-toolkit already installed (Phase 1 complete).
- The RTX 2070 Super (8 GB VRAM) is the only GPU and is not shared with other GPU-accelerated containers at inference time (Plex uses NVENC for transcoding, which is a separate hardware unit and does not conflict with CUDA compute).
- The `holygrail-proxy` Docker network already exists for Traefik integration (deployed in F2.2).
- Traefik is running and will pick up new Docker labels automatically.
- The default model is Llama 3.1 8B (or equivalent) — a model that fits in 8 GB VRAM while offering strong general-purpose capability. The specific model can be changed later without architectural changes.
- No authentication is required for the LLM API since it is LAN-only and the network is trusted (Constitution I: Local-First).
- Model downloads require a one-time internet connection; after that, the system operates fully offline per Constitution I.
- The LLM server will share HOLYGRAIL with existing services (Plex, monitoring, Traefik, Portainer) — resource contention during simultaneous Plex transcoding + LLM inference is acceptable for a single-user system.
