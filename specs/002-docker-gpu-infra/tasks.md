# Tasks: Docker & GPU Infrastructure

**Input**: Design documents from `/specs/002-docker-gpu-infra/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: No separate test tasks — the verification script (`verify-docker-gpu.sh`) serves as the post-implementation acceptance test, consistent with Constitution Principle IV (Test-After).

**Organization**: Tasks grouped by user story. US1 (GPU drivers) and US2 (Docker) can be installed in parallel on HOLYGRAIL since they're independent. US3 (GPU container toolkit) requires both US1 and US2. US4 (Portainer) requires US2 only.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create directory structure and write all scripts/configs in the repo before touching HOLYGRAIL.

- [x] T001 Create directory structure: `infrastructure/holygrail/docker/` and `infrastructure/holygrail/gpu/`

---

## Phase 2: Foundational (Script & Config Authoring)

**Purpose**: Author all install scripts, config files, and the verification script on the Mac. These are committed to the repo and later copied to HOLYGRAIL.

- [x] T002 [P] Write NVIDIA driver install script in `infrastructure/holygrail/gpu/install-nvidia.sh` — must run `ubuntu-drivers devices` to detect the recommended driver, install the `-server` variant via `ubuntu-drivers install --gpgpu`, verify no desktop environment is pulled in, and prompt for reboot. Script must check for root/sudo.
- [x] T003 [P] Write Docker Engine install script in `infrastructure/holygrail/docker/install-docker.sh` — must remove conflicting packages (docker.io, podman-docker, containerd, runc), add Docker's official GPG key and apt source, install docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin, docker-compose-plugin, add `john` to the docker group, and enable the Docker service. Script must check for root/sudo.
- [x] T004 [P] Write NVIDIA Container Toolkit install script in `infrastructure/holygrail/gpu/install-nvidia-container-toolkit.sh` — must add the NVIDIA container toolkit GPG key and apt source, install nvidia-container-toolkit, run `nvidia-ctk runtime configure --runtime=docker` to register the nvidia runtime in daemon.json, and restart Docker. Script must check for root/sudo and verify both NVIDIA driver and Docker are already installed before proceeding.
- [x] T005 [P] Write Docker daemon config in `infrastructure/holygrail/docker/daemon.json` — nvidia runtime registered but NOT set as default. Include log driver config with json-file and max-size/max-file limits for container log rotation.
- [x] T006 [P] Write Portainer CE Compose file in `infrastructure/holygrail/docker/portainer-compose.yml` — Portainer CE container with HTTPS on port 9443, Docker socket mounted, portainer_data volume, restart: always. Omit port 8000 (Edge Agent not needed).
- [x] T007 [P] Write verification script in `infrastructure/holygrail/verify-docker-gpu.sh` — must check all acceptance criteria: nvidia-smi shows RTX 2070 Super, no desktop environment installed, Docker service running and enabled, `john` in docker group, docker compose available, nvidia runtime registered in Docker, GPU visible inside a test container, Portainer container running, Portainer accessible on port 9443, UFW rule for 9443 exists. Output PASS/FAIL per check with summary.

**Checkpoint**: All repo artifacts written and committed. Ready for HOLYGRAIL installation.

---

## Phase 3: User Story 1 — Install GPU Drivers (Priority: P1)

**Goal**: RTX 2070 Super recognized and hardware-accelerated under Ubuntu, headless preserved.

**Independent Test**: `nvidia-smi` shows GPU model, driver version, and memory.

- [x] T008 [US1] Copy GPU install script to HOLYGRAIL: `scp infrastructure/holygrail/gpu/install-nvidia.sh john@holygrail:~/`
- [x] T009 [US1] SSH into HOLYGRAIL, run `ubuntu-drivers devices` to confirm recommended driver version, then run `sudo ~/install-nvidia.sh`
- [x] T010 [US1] Reboot HOLYGRAIL: `ssh holygrail "sudo reboot"`, wait 60 seconds, reconnect
- [x] T011 [US1] Verify GPU driver: `ssh holygrail "nvidia-smi"` — must show RTX 2070 Super with driver version and CUDA version
- [x] T012 [US1] Verify headless preserved: `ssh holygrail "systemctl list-units --type=service | grep -iE 'gdm|lightdm|sddm|xorg'"` — must return empty (no display manager)

**Checkpoint**: GPU driver working. nvidia-smi shows RTX 2070 Super.

---

## Phase 4: User Story 2 — Install Docker Engine & Compose (Priority: P1)

**Goal**: Docker Engine running, `john` can manage containers without sudo, Compose available.

**Independent Test**: `docker run --rm hello-world` succeeds as `john` without sudo. `docker compose version` reports v2.

**Note**: Phase 3 and Phase 4 can run in parallel on HOLYGRAIL since GPU drivers and Docker are independent.

- [x] T013 [US2] Copy Docker install script to HOLYGRAIL: `scp infrastructure/holygrail/docker/install-docker.sh john@holygrail:~/`
- [x] T014 [US2] SSH into HOLYGRAIL and run `sudo ~/install-docker.sh`
- [x] T015 [US2] Log out and back in for docker group: `ssh holygrail "exit" && ssh holygrail`
- [x] T016 [US2] Verify Docker works without sudo: `ssh holygrail "docker run --rm hello-world"`
- [x] T017 [US2] Verify Compose: `ssh holygrail "docker compose version"` — must show Compose v2

**Checkpoint**: Docker running. `john` manages containers without sudo.

---

## Phase 5: User Story 3 — Enable GPU Access Inside Containers (Priority: P2)

**Goal**: Containers can access the RTX 2070 Super via GPU passthrough.

**Independent Test**: `docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi` shows the GPU inside the container.

- [x] T018 [US3] Copy NVIDIA container toolkit script and daemon.json to HOLYGRAIL: `scp infrastructure/holygrail/gpu/install-nvidia-container-toolkit.sh infrastructure/holygrail/docker/daemon.json john@holygrail:~/`
- [x] T019 [US3] SSH into HOLYGRAIL and run `sudo ~/install-nvidia-container-toolkit.sh`
- [x] T020 [US3] Verify nvidia runtime is registered: `ssh holygrail "docker info | grep -i nvidia"`
- [x] T021 [US3] Run GPU test container: `ssh holygrail "docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi"` — must show RTX 2070 Super inside container
- [x] T022 [US3] Verify GPU passthrough survives reboot: `ssh holygrail "sudo reboot"`, wait 60s, reconnect, re-run the GPU test container

**Checkpoint**: GPU passthrough working inside containers.

---

## Phase 6: User Story 4 — Deploy Container Management Web UI (Priority: P3)

**Goal**: Portainer CE accessible via HTTPS from Mac browser, showing all containers.

**Independent Test**: Open `https://192.168.10.129:9443` in Mac browser, log in, see running containers.

- [x] T023 [US4] Copy Portainer Compose file to HOLYGRAIL: `scp infrastructure/holygrail/docker/portainer-compose.yml john@holygrail:~/`
- [x] T024 [US4] Deploy Portainer on HOLYGRAIL: `ssh holygrail "cd ~ && docker compose -f portainer-compose.yml up -d"`
- [x] T025 [US4] Open UFW port for Portainer from LAN: `ssh holygrail "sudo ufw allow from 192.168.10.0/24 to any port 9443 proto tcp"`
- [x] T026 [US4] Access Portainer at `https://192.168.10.129:9443` from Mac browser, accept self-signed cert, create admin account
- [x] T027 [US4] Verify Portainer shows all running containers and matches `docker ps` output on HOLYGRAIL
- [x] T028 [US4] Verify Portainer survives reboot: `ssh holygrail "sudo reboot"`, wait 60s, access `https://192.168.10.129:9443` from Mac

**Checkpoint**: Portainer running, accessible from Mac, all containers visible.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Run full verification, final cleanup.

- [x] T029 Copy and run full verification script on HOLYGRAIL: `scp infrastructure/holygrail/verify-docker-gpu.sh john@holygrail:~/` then `ssh holygrail "chmod +x ~/verify-docker-gpu.sh && sudo ~/verify-docker-gpu.sh"` — all checks must PASS
- [x] T030 Final reboot and verify all components start automatically: GPU driver, Docker, Portainer, GPU container passthrough

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — all scripts authored before touching HOLYGRAIL
- **US1 — GPU Drivers (Phase 3)**: Depends on Phase 2 (needs install script)
- **US2 — Docker (Phase 4)**: Depends on Phase 2 (needs install script). **Can run in parallel with Phase 3.**
- **US3 — GPU Container Toolkit (Phase 5)**: Depends on BOTH Phase 3 AND Phase 4 (needs GPU driver + Docker)
- **US4 — Portainer (Phase 6)**: Depends on Phase 4 only (needs Docker). **Can run in parallel with Phase 5.**
- **Polish (Phase 7)**: Depends on all phases complete

### User Story Dependencies

```text
Phase 1 (Setup)
    │
    ▼
Phase 2 (Scripts)
    │
    ├──────────────────┐
    │                  │
    ▼                  ▼
Phase 3 (US1: GPU)  Phase 4 (US2: Docker)
    │                  │
    │                  ├──────────────────┐
    │                  │                  │
    └──────────────────┘                  ▼
              │                   Phase 6 (US4: Portainer)
              ▼
        Phase 5 (US3: GPU Containers)
              │
              ▼
        Phase 7 (Polish)
```

### Parallel Opportunities

- **Phase 2**: T002-T007 are all independent files — write all six in parallel
- **Phase 3 + Phase 4**: GPU driver install and Docker install are independent — run on HOLYGRAIL in parallel
- **Phase 5 + Phase 6**: GPU container toolkit and Portainer are independent (both need Docker, but not each other) — can run in parallel after Docker is installed

### Parallel Example: Phase 2 (Foundational)

```bash
# Launch all six authoring tasks together:
Task: "Write NVIDIA install script in infrastructure/holygrail/gpu/install-nvidia.sh"
Task: "Write Docker install script in infrastructure/holygrail/docker/install-docker.sh"
Task: "Write NVIDIA container toolkit script in infrastructure/holygrail/gpu/install-nvidia-container-toolkit.sh"
Task: "Write daemon.json in infrastructure/holygrail/docker/daemon.json"
Task: "Write Portainer compose in infrastructure/holygrail/docker/portainer-compose.yml"
Task: "Write verify script in infrastructure/holygrail/verify-docker-gpu.sh"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (directory structure)
2. Complete Phase 2: Foundational (write all scripts in parallel)
3. Complete Phase 3 + Phase 4 in parallel: GPU drivers + Docker
4. **STOP and VALIDATE**: `nvidia-smi` works, `docker run hello-world` works
5. This is the minimum viable infrastructure — GPU and containers both functional

### Full Delivery

6. Complete Phase 5: GPU container toolkit (bridges GPU + Docker)
7. Complete Phase 6: Portainer (management UI)
8. Complete Phase 7: Full verification and reboot test
9. Commit all artifacts to repo on the `002-docker-gpu-infra` branch

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- LLM-executable tasks: T001-T007 (repo file creation)
- Physical tasks requiring SSH to HOLYGRAIL: T008-T030
- GPU driver install (Phase 3) requires a reboot before proceeding
- Docker group membership requires re-login before testing
- Portainer requires UFW rule addition — Docker bypasses UFW by default
- Commit after completing each phase
