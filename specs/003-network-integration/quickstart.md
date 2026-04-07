# Quickstart: Camelot Network Integration

**Branch**: `003-network-integration` | **Date**: 2026-04-07

> Execution checklist for integrating HOLYGRAIL into management scripts and documentation.

## Prerequisites

- [ ] F1.1 and F1.2 complete — HOLYGRAIL at 192.168.10.129 with Docker, GPU, Portainer
- [ ] SSH key auth working: `ssh holygrail` connects without password
- [ ] Mac workstation has the repo checked out

## Step 1: Update Management Scripts

1. Edit `scripts/pi-status.sh`:
   - Add HOLYGRAIL to the DEVICES array
   - Add `::GPU::` section to the remote command block
   - Add GPU output parsing and display with color-coded temperatures

2. Edit `scripts/pi-update.sh`:
   - Add HOLYGRAIL to the HOSTS map
   - Update usage text

3. Test from Mac:
   ```bash
   bash scripts/pi-status.sh holygrail
   bash scripts/pi-status.sh all
   ```

## Step 2: Harden SSH

1. Run the SSH hardening script on HOLYGRAIL:
   ```bash
   ssh holygrail "sudo sed -i '/^PasswordAuthentication/d' /etc/ssh/sshd_config.d/hardening.conf"
   ssh holygrail "echo 'PasswordAuthentication no' | sudo tee -a /etc/ssh/sshd_config.d/hardening.conf"
   ssh holygrail "sudo systemctl restart ssh"
   ```

2. Test that password auth is rejected:
   ```bash
   ssh -o PubkeyAuthentication=no john@192.168.10.129
   # Should be rejected
   ```

3. Test that key auth still works:
   ```bash
   ssh holygrail "echo 'Key auth works'"
   ```

## Step 3: Update Infrastructure Documentation

1. Edit `docs/INFRASTRUCTURE.md`:
   - Update HOLYGRAIL IP from TBD to 192.168.10.129
   - Update OS to Ubuntu Server 24.04 LTS
   - Add deployed services (Docker, NVIDIA driver, Portainer)
   - Update Mermaid network diagram

## Step 4: Create Setup Guide

1. Write `docs/HOLYGRAIL-setup.md`:
   - Consolidate all F1.1 + F1.2 steps
   - Include hardware-specific notes (enp7s0, UEFI boot, RTX 2070S)
   - Make all commands copy-pasteable

## Step 5: Verify

- [ ] `bash scripts/pi-status.sh holygrail` shows GPU info
- [ ] `bash scripts/pi-status.sh all` includes HOLYGRAIL
- [ ] Password SSH to HOLYGRAIL is rejected
- [ ] Key SSH to HOLYGRAIL still works
- [ ] INFRASTRUCTURE.md matches live state
- [ ] HOLYGRAIL-setup.md is complete and reviewable
