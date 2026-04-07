# Tasks: Camelot Network Integration

**Input**: Design documents from `/specs/003-network-integration/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: No separate test tasks — manual verification after each story.

**Organization**: All 4 user stories are independent and can be worked in any order. US1 (management scripts) and US2 (SSH hardening) are both P1. US3 (docs) and US4 (setup guide) are documentation-only.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No setup needed — all target files already exist. This feature modifies existing scripts and creates new docs.

- [x] T001 Read existing `scripts/pi-status.sh` and `scripts/pi-update.sh` to understand current device array patterns and output format

---

## Phase 2: User Story 1 — Add HOLYGRAIL to Management Scripts (Priority: P1)

**Goal**: Status and update scripts include HOLYGRAIL with GPU and Docker reporting.

**Independent Test**: Run `bash scripts/pi-status.sh holygrail` from Mac and confirm GPU info appears.

- [x] T002 [US1] Add HOLYGRAIL entry `"HOLYGRAIL|192.168.10.129|john"` to the DEVICES array in `scripts/pi-status.sh`
- [x] T003 [US1] Add `::GPU::` section to the remote status command block in `scripts/pi-status.sh` — use `nvidia-smi --query-gpu=name,temperature.gpu,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits` if nvidia-smi is available, otherwise output "N/A"
- [x] T004 [US1] Add GPU output parsing and display to the section parser in `scripts/pi-status.sh` — show GPU model, temperature (green <60°C, yellow 60-80°C, red >80°C), memory usage, and utilization
- [x] T005 [US1] Add HOLYGRAIL entry `[holygrail]="HOLYGRAIL|192.168.10.129|john"` to the HOSTS map in `scripts/pi-update.sh`
- [x] T006 [US1] Update the usage text in `scripts/pi-update.sh` to include `holygrail` as a valid target
- [x] T007 [US1] Test `bash scripts/pi-status.sh holygrail` from Mac — verify GPU temp, memory, Docker containers appear
- [x] T008 [US1] Test `bash scripts/pi-status.sh all` from Mac — verify HOLYGRAIL appears alongside all Pis without errors

**Checkpoint**: Management scripts report HOLYGRAIL status including GPU info.

---

## Phase 3: User Story 2 — Harden SSH to Key-Only (Priority: P1)

**Goal**: Password authentication disabled on HOLYGRAIL, key-only SSH.

**Independent Test**: `ssh -o PubkeyAuthentication=no john@192.168.10.129` is rejected.

- [x] T009 [US2] Write SSH hardening script in `infrastructure/holygrail/harden-ssh.sh` — adds `PasswordAuthentication no` to `/etc/ssh/sshd_config.d/hardening.conf` and restarts `ssh` service. Must check for root/sudo. CRITICAL SAFETY: Before disabling password auth, the script must test that key-based SSH works by checking if the current session is key-authenticated (via SSH_AUTH_SOCK or ssh-add -l). If key auth cannot be confirmed, abort with an error and instructions to set up SSH keys first.
- [x] T010 [US2] Run the hardening script on HOLYGRAIL via SSH: `scp infrastructure/holygrail/harden-ssh.sh john@holygrail:~/ && ssh holygrail "chmod +x ~/harden-ssh.sh && sudo ~/harden-ssh.sh"`
- [x] T011 [US2] Verify key-based SSH still works: `ssh holygrail "echo 'Key auth OK'"`
- [x] T012 [US2] Verify password SSH is rejected: `ssh -o PubkeyAuthentication=no -o BatchMode=yes john@192.168.10.129 "echo fail" 2>&1` — must fail with permission denied
- [x] T013 [US2] Verify SSH hardening persists after reboot: `ssh holygrail "sudo reboot"`, wait 30s, reconnect and re-test

**Checkpoint**: HOLYGRAIL accepts only key-based SSH.

---

## Phase 4: User Story 3 — Update Infrastructure Documentation (Priority: P2)

**Goal**: INFRASTRUCTURE.md reflects HOLYGRAIL's live configuration with zero discrepancies.

**Independent Test**: Compare every HOLYGRAIL detail in the docs against `ssh holygrail` output.

- [x] T014 [P] [US3] Update HOLYGRAIL section in `docs/INFRASTRUCTURE.md` — set IP to 192.168.10.129, OS to Ubuntu Server 24.04 LTS, list deployed services (Docker 29.4.0, NVIDIA driver 570, Portainer CE on port 9443), network interface enp7s0, hostname holygrail
- [x] T015 [P] [US3] Update the Mermaid network diagram in `docs/INFRASTRUCTURE.md` — add HOLYGRAIL at 192.168.10.129 with its role and connections
- [x] T016 [US3] Verify all HOLYGRAIL details in `docs/INFRASTRUCTURE.md` match live state by running `ssh holygrail "hostname && ip addr show enp7s0 | grep inet && nvidia-smi --query-gpu=name,driver_version --format=csv,noheader && docker --version && docker compose version"`

**Checkpoint**: Documentation matches live HOLYGRAIL state.

---

## Phase 5: User Story 4 — Create HOLYGRAIL Setup Guide (Priority: P3)

**Goal**: Comprehensive, reproducible setup guide documenting all Phase 1 work.

**Independent Test**: A knowledgeable admin could follow the guide to rebuild HOLYGRAIL from scratch.

- [x] T017 [US4] Create `docs/HOLYGRAIL-setup.md` with the following sections: Prerequisites (hardware, BIOS/UEFI settings), Ubuntu Server Install (USB creation, Subiquity options, hostname, user, SSH), Post-Install Configuration (static IP 192.168.10.129 on enp7s0, timezone America/Denver, UFW SSH-only, SSH hardening), NVIDIA GPU Driver (ubuntu-drivers install, nvidia-smi verification), Docker Engine (official apt repo install, john in docker group, Compose v2), NVIDIA Container Toolkit (repo setup, nvidia-ctk runtime configure, GPU container test), Portainer CE (compose deployment, UFW port 9443, HTTPS access). All commands must be copy-pasteable with actual values used on this machine.
- [x] T018 [US4] Add hardware-specific notes to `docs/HOLYGRAIL-setup.md` — BIOS UEFI boot (AM5 board), network interface name `enp7s0`, RTX 2070 Super PCIe slot, Pi-hole DNS at 192.168.10.150 with 8.8.8.8 fallback

**Checkpoint**: Setup guide complete and reviewable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T019 Update `docs/INFRASTRUCTURE.md` Pi-hole reference — Pi-hole is at 192.168.10.150 (media server), not 192.168.10.105 (NAS), if not already corrected in that file
- [x] T020 Final verification: run `bash scripts/pi-status.sh all` and confirm all 4 devices report status without errors

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — read existing scripts
- **US1 — Scripts (Phase 2)**: Depends on Phase 1
- **US2 — SSH Hardening (Phase 3)**: Independent of all other phases
- **US3 — Docs (Phase 4)**: Independent (can run in parallel with Phase 2/3)
- **US4 — Setup Guide (Phase 5)**: Independent (can run in parallel with all)
- **Polish (Phase 6)**: Depends on Phases 2-5

### User Story Dependencies

```text
Phase 1 (Read scripts)
    │
    ├────────────────┬──────────────────┬──────────────────┐
    │                │                  │                  │
    ▼                ▼                  ▼                  ▼
Phase 2 (US1)    Phase 3 (US2)    Phase 4 (US3)    Phase 5 (US4)
    │                │                  │                  │
    └────────────────┴──────────────────┴──────────────────┘
                              │
                              ▼
                      Phase 6 (Polish)
```

### Parallel Opportunities

- **All 4 user stories** are independent — they can run in parallel
- **Phase 4**: T014 and T015 modify different sections of the same file — can be done in parallel if careful
- **Phase 5**: T017 and T018 are sequential (T018 adds to T017's output)

---

## Implementation Strategy

### MVP First (US1)

1. Complete Phase 1: Read existing scripts
2. Complete Phase 2: Add HOLYGRAIL to management scripts
3. **STOP and VALIDATE**: `bash scripts/pi-status.sh holygrail` shows GPU info
4. This alone delivers unified management from the Mac

### Full Delivery

5. Complete Phase 3: SSH hardening (key-only)
6. Complete Phase 4: Update INFRASTRUCTURE.md
7. Complete Phase 5: Create setup guide
8. Complete Phase 6: Final verification
9. Commit on `003-network-integration` branch

---

## Notes

- All tasks are LLM-executable (script editing, doc writing, SSH commands)
- SSH hardening (US2) is the only task that modifies HOLYGRAIL's configuration
- The setup guide (US4) should reference the actual scripts in `infrastructure/holygrail/` rather than inlining commands
- Commit after completing each phase
