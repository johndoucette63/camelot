# Implementation Plan: Ubuntu Migration & Base Setup

**Branch**: `001-ubuntu-migration` | **Date**: 2026-04-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-ubuntu-migration/spec.md`

## Summary

Wipe HOLYGRAIL (Windows 11) and install Ubuntu Server 24.04 LTS as a headless server with SSH access, static IP (192.168.10.129), host firewall, and Pi-hole DNS. This is a manual, one-time infrastructure migration — no automation tooling, no autoinstall. The admin performs an interactive install, then runs a post-install configuration script and verifies all acceptance criteria.

## Technical Context

**Language/Version**: Bash (POSIX-compatible shell scripts)
**Primary Dependencies**: Ubuntu Server 24.04 LTS, OpenSSH, UFW, Netplan 1.0
**Storage**: N/A (OS-level disk, no application storage)
**Testing**: Verification shell script that checks all acceptance criteria post-install
**Target Platform**: x86_64 (AMD Ryzen 7800X3D, AM5/UEFI)
**Project Type**: Infrastructure migration (OS install + configuration)
**Performance Goals**: N/A (base OS, no application performance targets)
**Constraints**: Must be completable with physical access to HOLYGRAIL; headless operation begins after first SSH connection
**Scale/Scope**: Single server, single admin

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Local-First | PASS | Everything on 192.168.10.0/24. No cloud dependencies. DNS through local Pi-hole. |
| II. Simplicity & Pragmatism | PASS | Manual interactive install (no autoinstall/cloud-init). One post-install shell script. YAGNI applied throughout. |
| III. Containerized Everything | N/A | This feature is base OS setup. Docker and containers are a separate Phase 1 feature. |
| IV. Test-After | PASS | Verification script runs after all configuration is applied. No test-first. |
| V. Observability | DEFERRED | OS-level logging (journald/syslog) is available by default. Service-level observability is a later phase concern. |
| Prohibited Technologies | PASS | No Kubernetes, no cloud services, no CI/CD, no GraphQL. |
| Dev Workflow | PASS | Scripts and configs committed to repo. Single developer, direct commits. |

**Post-Phase 1 Re-check**: PASS — No changes to constitution compliance. All configuration files live in the repo, scripts are small and focused, no enterprise patterns introduced.

## Project Structure

### Documentation (this feature)

```text
specs/001-ubuntu-migration/
├── plan.md              # This file
├── research.md          # Phase 0: installation & config research
├── data-model.md        # Phase 1: configuration entities
├── quickstart.md        # Phase 1: step-by-step execution guide
└── tasks.md             # Phase 2 output (/speckit.tasks - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
infrastructure/
└── holygrail/
    ├── post-install.sh          # Post-install config script (SSH, firewall, network, hostname)
    ├── verify-install.sh        # Verification script for all acceptance criteria
    └── netplan/
        └── 01-static-ip.yaml   # Netplan config template for 192.168.10.129/24

scripts/
└── ssh-config                   # Updated with holygrail entry (192.168.10.129)
```

**Structure Decision**: Configuration files and scripts live under `infrastructure/holygrail/` following the existing repo convention (`infrastructure/torrentbox/`, `infrastructure/monitoring/`). The `scripts/ssh-config` is updated to replace the TBD IP with 192.168.10.129.

## Complexity Tracking

No constitution violations. Table not needed.
