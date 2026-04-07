# Implementation Plan: Docker & GPU Infrastructure

**Branch**: `002-docker-gpu-infra` | **Date**: 2026-04-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-docker-gpu-infra/spec.md`

## Summary

Install NVIDIA GPU drivers (server variant, no desktop), Docker Engine from the official apt repo, NVIDIA Container Toolkit for GPU passthrough into containers, and Portainer CE for web-based container management. No CUDA toolkit on the host — container images bundle their own CUDA runtime. Container ports bound to localhost by default; Portainer exposed to LAN via UFW rule.

## Technical Context

**Language/Version**: Bash (POSIX-compatible shell scripts)
**Primary Dependencies**: NVIDIA driver (560-server), Docker Engine, Docker Compose v2, nvidia-container-toolkit, Portainer CE
**Storage**: Docker volumes for Portainer data; no application databases
**Testing**: Verification shell script (checks GPU, Docker, container GPU passthrough, Portainer)
**Target Platform**: x86_64 (AMD Ryzen 7800X3D, RTX 2070 Super, Ubuntu Server 24.04 LTS)
**Project Type**: Infrastructure setup (driver + runtime + container management)
**Performance Goals**: N/A (infrastructure layer, no application performance targets)
**Constraints**: Headless only (no desktop/X11), official repos only (no Snap), container ports bound to localhost by default
**Scale/Scope**: Single server, single GPU, single admin

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Local-First | PASS | All packages from official repos, all services on LAN. Portainer accessible only from 192.168.10.0/24. |
| II. Simplicity | PASS | Minimal installs: driver-only (no CUDA toolkit on host), standard Docker install, single Portainer container. |
| III. Containerized Everything | PASS | Docker Engine + Compose installed. Portainer itself runs as a container with restart=always. GPU runtime opt-in per container. |
| IV. Test-After | PASS | Verification script runs after all installations complete. |
| V. Observability | PASS | Portainer provides container status monitoring. nvidia-smi available for GPU health. Detailed monitoring deferred to Phase 2/8. |
| Prohibited Technologies | PASS | No Kubernetes, no cloud services, no CI/CD. |
| Dev Workflow | PASS | Install scripts committed to repo. Single developer, direct commits. |

**Post-Phase 1 Re-check**: PASS — No violations. Docker is the ceiling per constitution (no Swarm/K8s). GPU runtime is opt-in, not default, keeping containers simple.

## Project Structure

### Documentation (this feature)

```text
specs/002-docker-gpu-infra/
├── plan.md              # This file
├── research.md          # Phase 0: driver, Docker, GPU toolkit research
├── data-model.md        # Phase 1: configuration entities
├── quickstart.md        # Phase 1: step-by-step execution guide
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
infrastructure/
└── holygrail/
    ├── docker/
    │   ├── install-docker.sh       # Docker Engine + Compose installation
    │   ├── daemon.json             # Docker daemon config (nvidia runtime)
    │   └── portainer-compose.yml   # Portainer CE Docker Compose file
    ├── gpu/
    │   ├── install-nvidia.sh       # NVIDIA driver installation (server variant)
    │   └── install-nvidia-container-toolkit.sh  # Container GPU passthrough
    └── verify-docker-gpu.sh        # Verification script for all F1.2 acceptance criteria
```

**Structure Decision**: Scripts and configs under `infrastructure/holygrail/` following F1.1 convention. Subdivided into `docker/` and `gpu/` for clarity since this feature has two distinct subsystems. Verification script at the holygrail root level alongside `verify-install.sh` from F1.1.

## Complexity Tracking

No constitution violations. Table not needed.
