# Research: Camelot Network Integration

**Branch**: `003-network-integration` | **Date**: 2026-04-07

## Decision 1: Script Architecture for HOLYGRAIL Support

**Decision**: Add HOLYGRAIL to the existing device arrays in pi-status.sh and pi-update.sh, with conditional GPU reporting for x86_64 hosts.

**Rationale**: Both scripts use a device array pattern (`DEVICES=()` in status, `declare -A HOSTS` in update). Adding HOLYGRAIL follows the same pattern. GPU temperature uses `nvidia-smi` (not `vcgencmd` which is Pi-specific). The status script's SSH command block needs a GPU section that gracefully handles nvidia-smi not being available (for Pis) while reporting it for HOLYGRAIL.

**Alternatives considered**: Separate HOLYGRAIL-specific scripts — rejected per constitution (simplicity, one script per task, avoid duplication).

## Decision 2: GPU Status Reporting Format

**Decision**: Add `::GPU::` section to the status script's remote command block. Report GPU model, temperature, memory usage, and GPU utilization. Skip gracefully on devices without nvidia-smi.

**Rationale**: The existing script uses `::SECTION::` delimiters parsed by the display loop. Adding `::GPU::` follows the same pattern. nvidia-smi's `--query-gpu` flag provides structured output. GPU temp color thresholds: green <60°C, yellow 60-80°C, red >80°C (standard for desktop GPUs, higher than Pi thresholds).

**Alternatives considered**: Separate GPU monitoring script — rejected (same reason as above).

## Decision 3: SSH Hardening Approach

**Decision**: Create a small `harden-ssh.sh` script that sets `PasswordAuthentication no` in the existing `/etc/ssh/sshd_config.d/hardening.conf` drop-in file (created in F1.1) and restarts the SSH service.

**Rationale**: The drop-in file already exists from F1.1 with `PermitRootLogin no`. Adding `PasswordAuthentication no` to the same file keeps all hardening in one place. This is a one-line change + service restart.

**Alternatives considered**: Editing sshd_config directly — rejected because the drop-in approach is cleaner and survives package upgrades.

## Decision 4: Documentation Approach

**Decision**: Update INFRASTRUCTURE.md in-place with HOLYGRAIL's live details. Create a new `docs/HOLYGRAIL-setup.md` as a standalone setup guide.

**Rationale**: INFRASTRUCTURE.md is the canonical network reference — it must reflect reality. The setup guide is a separate document because it serves a different purpose (disaster recovery vs. reference). The setup guide will consolidate all F1.1 + F1.2 steps into a single reproducible walkthrough.

**Alternatives considered**: Putting setup instructions in INFRASTRUCTURE.md — rejected because it would make the reference doc too long and mix operational procedures with configuration reference.
