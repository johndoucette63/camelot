# Tasks: Ubuntu Migration & Base Setup

**Input**: Design documents from `/specs/001-ubuntu-migration/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: No separate test tasks — the verification script (`verify-install.sh`) serves as the post-implementation acceptance test, consistent with Constitution Principle IV (Test-After).

**Organization**: Tasks are grouped by user story. Note that US2 (Create Bootable Installer) must execute before US1 (Install Ubuntu) physically, even though US1 is higher priority — US2 is a prerequisite for US1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create directory structure for HOLYGRAIL infrastructure configs

- [x] T001 Create directory structure: `infrastructure/holygrail/` and `infrastructure/holygrail/netplan/`

---

## Phase 2: Foundational (Script & Config Authoring)

**Purpose**: Write all scripts and config files in the repo before touching HOLYGRAIL. These are authored on the Mac and later copied to the server.

- [x] T002 [P] Write netplan static IP configuration in `infrastructure/holygrail/netplan/01-static-ip.yaml` — static IP 192.168.10.129/24, gateway 192.168.10.1, DNS 192.168.10.150, using Netplan 1.0 `routes` block syntax. Include a comment noting the interface name (`enp*`) must be verified with `ip link` on HOLYGRAIL.
- [x] T003 [P] Write post-install configuration script in `infrastructure/holygrail/post-install.sh` — must set hostname to `holygrail`, set timezone (prompt or accept argument), copy netplan config to `/etc/netplan/`, run `netplan apply`, create `/etc/ssh/sshd_config.d/hardening.conf` with `PermitRootLogin no`, restart `ssh` service, configure UFW (default deny incoming, allow outgoing, allow ssh, enable), and reboot. Script must be idempotent and check for root/sudo before running.
- [x] T004 [P] Write verification script in `infrastructure/holygrail/verify-install.sh` — must check all acceptance criteria: hostname is `holygrail`, static IP is 192.168.10.129, DNS resolves through 192.168.10.150, timezone is set, SSH is accessible, root SSH login is denied (`PermitRootLogin no` in sshd config), password authentication is enabled (`PasswordAuthentication yes` in sshd config, per FR-007), UFW is active with SSH-only rule, `john` user has sudo privileges. Output PASS/FAIL for each check with a summary.

**Checkpoint**: All repo artifacts written and committed. Ready for physical migration.

---

## Phase 3: User Story 2 — Create Bootable Ubuntu Installer (Priority: P2)

**Goal**: Produce a verified bootable USB drive with Ubuntu Server 24.04 LTS.

**Independent Test**: Boot HOLYGRAIL from the USB and confirm the Ubuntu Server installer screen loads.

- [x] T005 [US2] Download Ubuntu Server 24.04 LTS ISO on Mac from the official Ubuntu releases page
- [x] T006 [US2] Verify the downloaded ISO's SHA256 checksum matches the official published hash
- [x] T007 [US2] Write the verified ISO to a USB drive using `dd` or balenaEtcher on Mac
- [x] T008 [US2] Boot HOLYGRAIL from the USB drive (UEFI boot menu, typically F8/F12) and confirm the Subiquity installer loads successfully

**Checkpoint**: Bootable USB verified. Ready for OS installation.

---

## Phase 4: User Story 1 — Install Ubuntu Server Headless (Priority: P1)

**Goal**: HOLYGRAIL running Ubuntu Server 24.04 LTS with SSH access for the `john` user.

**Independent Test**: SSH into HOLYGRAIL from the Mac workstation and confirm `john` has sudo, root login is denied.

- [x] T009 [US1] Complete Ubuntu Server 24.04 LTS minimal install via Subiquity — accept default GPT/EFI partitioning, set hostname `holygrail`, create user `john` with password, enable OpenSSH server, skip SSH key import
- [x] T010 [US1] After first boot, find HOLYGRAIL's DHCP-assigned IP (check Pi-hole DHCP leases or read from console) and verify SSH access: `ssh john@<dhcp-ip>`
- [x] T011 [US1] Verify `john` has sudo privileges (`sudo whoami` returns `root`) and root SSH is denied (`ssh root@<dhcp-ip>` is rejected)

**Checkpoint**: Ubuntu installed and remotely accessible via SSH. Monitor/keyboard still connected as fallback.

---

## Phase 5: User Story 3 — Configure Hostname, Static IP, and Timezone (Priority: P2)

**Goal**: HOLYGRAIL at static IP 192.168.10.129 with correct hostname, timezone, DNS through Pi-hole, and firewall allowing SSH only.

**Independent Test**: Reboot HOLYGRAIL, reconnect at 192.168.10.129, run verification script — all checks pass.

- [x] T012 [US3] Copy `infrastructure/holygrail/post-install.sh` and `infrastructure/holygrail/netplan/01-static-ip.yaml` to HOLYGRAIL via SCP: `scp infrastructure/holygrail/post-install.sh infrastructure/holygrail/netplan/01-static-ip.yaml john@<dhcp-ip>:~/`
- [x] T013 [US3] SSH into HOLYGRAIL, verify the network interface name with `ip link`, update the netplan config if the interface name differs from the template, then run `sudo ~/post-install.sh`
- [x] T014 [US3] After reboot, reconnect at static IP: `ssh john@192.168.10.129`
- [x] T015 [US3] Copy and run verification script: `scp infrastructure/holygrail/verify-install.sh john@192.168.10.129:~/` then `ssh john@192.168.10.129 "chmod +x ~/verify-install.sh && sudo ~/verify-install.sh"` — all checks must PASS
- [x] T016 [US3] Reboot HOLYGRAIL two more times (3 total with static IP: post-install reboot + 2 here), reconnecting at 192.168.10.129 each time. After the final boot verify: static IP persists, hostname returns `holygrail`, UFW shows active with SSH rule. This satisfies SC-002 (3 consecutive reboots).

**Checkpoint**: All configuration applied and verified across reboots. HOLYGRAIL is production-ready as a base server.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Update repo references, finalize headless operation, clean up.

- [x] T017 [P] Update `scripts/ssh-config` — replace HOLYGRAIL's TBD IP with `192.168.10.129` and ensure the `holygrail` host alias is configured
- [x] T018 Verify headless SSH workflow from Mac using the ssh-config alias: `ssh holygrail` connects successfully to 192.168.10.129
- [x] T019 Disconnect monitor and keyboard from HOLYGRAIL — server is fully headless from this point forward
- [x] T020 Run final quickstart.md validation — confirm all 9 steps have been completed successfully

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS physical migration (scripts must be written first)
- **US2 — Bootable Installer (Phase 3)**: Depends on Phase 1 only (no scripts needed for USB creation). Can run in parallel with Phase 2.
- **US1 — Install Ubuntu (Phase 4)**: Depends on Phase 3 (needs bootable USB)
- **US3 — Configure Network (Phase 5)**: Depends on Phase 2 (needs scripts) AND Phase 4 (needs Ubuntu installed)
- **Polish (Phase 6)**: Depends on Phase 5 completion

### User Story Dependencies

```text
Phase 1 (Setup)
    │
    ├──────────────────┐
    │                  │
    ▼                  ▼
Phase 2 (Scripts)   Phase 3 (US2: USB)
    │                  │
    │                  ▼
    │              Phase 4 (US1: Install)
    │                  │
    └──────────────────┘
              │
              ▼
        Phase 5 (US3: Configure)
              │
              ▼
        Phase 6 (Polish)
```

### Parallel Opportunities

- **Phase 2**: T002, T003, T004 are all independent files — write all three in parallel
- **Phase 2 + Phase 3**: Script authoring (Phase 2) and USB creation (Phase 3) can run in parallel since they're independent activities
- **Phase 6**: T017 (ssh-config update) can be done in parallel with T018-T020

### Parallel Example: Phase 2 (Foundational)

```bash
# Launch all three script/config authoring tasks together:
Task: "Write netplan config in infrastructure/holygrail/netplan/01-static-ip.yaml"
Task: "Write post-install script in infrastructure/holygrail/post-install.sh"
Task: "Write verify script in infrastructure/holygrail/verify-install.sh"
```

---

## Implementation Strategy

### MVP First (US2 + US1)

1. Complete Phase 1: Setup (directory structure)
2. Complete Phase 3: US2 (create bootable USB) — can run in parallel with Phase 2
3. Complete Phase 2: Foundational (write scripts)
4. Complete Phase 4: US1 (install Ubuntu, verify SSH)
5. **STOP and VALIDATE**: SSH into HOLYGRAIL, confirm base OS is running
6. This is the minimum viable migration — server is remotely accessible

### Full Delivery

7. Complete Phase 5: US3 (apply all configuration, run verification)
8. Complete Phase 6: Polish (update repo, go headless)
9. Commit all artifacts to repo on the `001-ubuntu-migration` branch

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Physical tasks (T005-T016) require hands-on access to HOLYGRAIL and cannot be automated by an LLM
- Repo tasks (T001-T004, T017) are LLM-executable
- Commit after completing each phase
- The post-install script must be idempotent — safe to re-run if something goes wrong
- Keep monitor/keyboard connected until Phase 5 checkpoint passes (T016) as a recovery fallback
