# Quickstart: Ubuntu Migration & Base Setup

**Branch**: `001-ubuntu-migration` | **Date**: 2026-04-06

> Step-by-step execution guide for migrating HOLYGRAIL from Windows 11 to Ubuntu Server 24.04 LTS. Intended to be followed sequentially.

## Prerequisites

- [ ] USB drive (8GB+) available
- [ ] Keyboard and monitor connected to HOLYGRAIL (temporary, for install only)
- [ ] HOLYGRAIL connected to LAN via Ethernet
- [ ] Mac workstation on the same 192.168.10.0/24 network
- [ ] Pi-hole / NAS at 192.168.10.150 is online

## Step 1: Create Bootable USB (on Mac)

1. Download Ubuntu Server 24.04 LTS ISO from the official site
2. Verify the SHA256 checksum matches the published hash
3. Write the ISO to USB using `dd` or balenaEtcher
4. Safely eject the USB drive

## Step 2: Install Ubuntu Server (on HOLYGRAIL)

1. Insert USB into HOLYGRAIL, power on
2. Enter UEFI boot menu (typically F8 or F12, depends on motherboard)
3. Select the USB drive to boot from
4. In the Subiquity installer:
   - Choose **minimal install**
   - Accept default disk partitioning (GPT + EFI, single root partition)
   - Set hostname: `holygrail`
   - Create user: `john` (with password)
   - Enable **OpenSSH server** when prompted
   - Skip importing SSH keys (will configure later)
5. Complete the install, remove USB, reboot

## Step 3: Verify Initial SSH Access (from Mac)

1. Find HOLYGRAIL's DHCP-assigned IP (check router/Pi-hole DHCP leases, or use the console)
2. Test SSH: `ssh john@<dhcp-ip>`
3. Confirm login succeeds — all remaining steps are done over SSH

## Step 4: Copy Post-Install Script to HOLYGRAIL (from Mac)

```bash
scp infrastructure/holygrail/post-install.sh john@<dhcp-ip>:~/
scp infrastructure/holygrail/netplan/01-static-ip.yaml john@<dhcp-ip>:~/
```

## Step 5: Run Post-Install Configuration (on HOLYGRAIL via SSH)

```bash
chmod +x ~/post-install.sh
sudo ~/post-install.sh
```

The script will:
- Set hostname to `holygrail`
- Set timezone to the admin's local timezone
- Apply static IP configuration (192.168.10.129/24) via Netplan
- Disable root SSH login (`PermitRootLogin no`)
- Enable UFW with SSH-only inbound rule
- Reboot the system

## Step 6: Reconnect at Static IP (from Mac)

After reboot, HOLYGRAIL should be at its new static IP:

```bash
ssh john@192.168.10.129
```

## Step 7: Run Verification Script (on HOLYGRAIL)

```bash
scp infrastructure/holygrail/verify-install.sh john@192.168.10.129:~/
ssh john@192.168.10.129 "chmod +x ~/verify-install.sh && sudo ~/verify-install.sh"
```

The script checks all acceptance criteria:
- Hostname is `holygrail`
- Static IP is 192.168.10.129
- DNS resolves through 192.168.10.150
- Timezone is set correctly
- SSH is accessible, root login is denied
- UFW is active with SSH-only rule
- `john` user has sudo privileges

## Step 8: Update Repo SSH Config (on Mac)

Update `scripts/ssh-config` to replace the TBD IP with 192.168.10.129, then update local SSH config:

```bash
# After editing scripts/ssh-config:
cp scripts/ssh-config ~/.ssh/config.d/camelot  # or include in ~/.ssh/config
ssh holygrail  # should connect to 192.168.10.129
```

## Step 9: Disconnect Monitor and Keyboard

HOLYGRAIL is now fully headless. All future management is via SSH from the Mac workstation.

## Post-Migration

- Commit all configuration files and updated ssh-config to the repo
- Mark F1.1 as complete in `docs/PROJECT-PLAN.md`
- Proceed to next Phase 1 features (Docker, NVIDIA drivers, Portainer)
