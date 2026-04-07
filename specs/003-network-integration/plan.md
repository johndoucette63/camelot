# Implementation Plan: Camelot Network Integration

**Branch**: `003-network-integration` | **Date**: 2026-04-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-network-integration/spec.md`

## Summary

Integrate HOLYGRAIL into the existing Camelot management scripts (pi-status.sh, pi-update.sh) with GPU and Docker status reporting, harden SSH to key-only authentication, update INFRASTRUCTURE.md to reflect live state, and create a comprehensive HOLYGRAIL setup guide for disaster recovery.

## Technical Context

**Language/Version**: Bash (POSIX-compatible shell scripts), Markdown documentation
**Primary Dependencies**: Existing pi-status.sh/pi-update.sh scripts, OpenSSH, nvidia-smi, Docker CLI
**Storage**: N/A
**Testing**: Manual verification — run scripts, attempt password SSH, compare docs to live state
**Target Platform**: macOS (script execution) + Ubuntu Server 24.04 LTS (HOLYGRAIL target)
**Project Type**: Script modification + documentation
**Performance Goals**: Status script completes HOLYGRAIL check within 15 seconds
**Constraints**: Scripts must remain compatible with existing Pi devices (ARM64) while supporting HOLYGRAIL (x86_64)
**Scale/Scope**: 4 files modified, 1 new doc created, 1 SSH config change on HOLYGRAIL

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Local-First | PASS | All scripts run locally on LAN. No cloud dependencies. |
| II. Simplicity | PASS | Extending existing scripts, not creating new frameworks. One script per task. |
| III. Containerized Everything | N/A | Management scripts run on the Mac, not in containers. |
| IV. Test-After | PASS | Manual verification after changes. |
| V. Observability | PASS | This feature IS about observability — adding HOLYGRAIL health monitoring. |
| Prohibited Technologies | PASS | No new technologies introduced. |
| Dev Workflow | PASS | Direct edits to existing scripts. |

**Post-Phase 1 Re-check**: PASS — No changes to compliance.

## Project Structure

### Documentation (this feature)

```text
specs/003-network-integration/
├── plan.md              # This file
├── research.md          # Phase 0: script structure analysis
├── data-model.md        # Phase 1: device/script entities
├── quickstart.md        # Phase 1: execution checklist
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
scripts/
├── pi-status.sh         # MODIFY: Add HOLYGRAIL with GPU/Docker reporting
└── pi-update.sh         # MODIFY: Add HOLYGRAIL target

infrastructure/
└── holygrail/
    └── harden-ssh.sh    # NEW: Disable password auth, key-only

docs/
├── INFRASTRUCTURE.md    # MODIFY: Update HOLYGRAIL details
└── HOLYGRAIL-setup.md   # NEW: Complete Phase 1 setup guide
```

**Structure Decision**: Modify existing scripts in-place. New SSH hardening script under `infrastructure/holygrail/`. New setup guide under `docs/`.

## Complexity Tracking

No constitution violations. Table not needed.
