# HOLYGRAIL Setup Guide

Complete Phase 1 build guide for HOLYGRAIL — the Camelot central server. Follow these steps to reproduce the current configuration from a bare machine.

**Hardware**: AMD Ryzen 7 7800X3D, 32GB DDR5, NVIDIA RTX 2070 Super, 1TB NVMe SSD  
**Target OS**: Ubuntu Server 24.04 LTS  
**Final IP**: 192.168.10.129  
**Network Interface**: enp7s0

---

## 1. Create Bootable USB (on Mac)

1. Download Ubuntu Server 24.04 LTS ISO from https://ubuntu.com/download/server
2. Verify SHA256 checksum:
   ```bash
   shasum -a 256 ubuntu-24.04*-live-server-amd64.iso
   ```
3. Write to USB (replace `diskN` with your USB device):
   ```bash
   sudo dd if=ubuntu-24.04*-live-server-amd64.iso of=/dev/rdiskN bs=1m status=progress
   ```
4. Eject USB safely.

## 2. BIOS/UEFI Settings

- AM5 motherboard — UEFI only (no Legacy/CSM needed)
- Boot menu: typically **F8** or **F12** (varies by motherboard vendor)
- Secure Boot: leave enabled (Ubuntu supports it)
- No special GPU settings needed

## 3. Install Ubuntu Server

1. Boot from USB via UEFI boot menu
2. In the Subiquity installer:
   - Language: English
   - Install: **Ubuntu Server (minimized)**
   - Network: Leave as DHCP (static IP configured post-install)
   - Disk: Accept defaults — GPT + EFI + single LVM root partition
   - Hostname: `holygrail`
   - Username: `john`
   - Password: set a strong password
   - SSH: **Enable OpenSSH server**
   - Skip SSH key import
   - No additional snaps
3. Complete install, remove USB, reboot

## 4. Initial SSH Access

1. Find HOLYGRAIL's DHCP-assigned IP from your router or Pi-hole DHCP leases
2. From Mac:
   ```bash
   ssh john@<dhcp-ip>
   ```
3. Install OpenSSH if not already present:
   ```bash
   sudo apt update && sudo apt install -y openssh-server
   ```

## 5. Post-Install Configuration

Copy the post-install script from the repo and run it:

```bash
# From Mac:
scp infrastructure/holygrail/post-install.sh john@<dhcp-ip>:~/
scp infrastructure/holygrail/netplan/01-static-ip.yaml john@<dhcp-ip>:~/

# On HOLYGRAIL:
ssh john@<dhcp-ip>
```

**Verify network interface name** before running:
```bash
ip link
# Look for the Ethernet interface — on this machine it's enp7s0
# If different, edit ~/01-static-ip.yaml and replace enp7s0
```

Run the post-install script:
```bash
sudo ~/post-install.sh America/Denver
```

This sets:
- Hostname: `holygrail`
- Timezone: America/Denver
- Static IP: 192.168.10.129/24 (gateway 192.168.10.1)
- DNS: Pi-hole (192.168.10.150) + 8.8.8.8 fallback
- SSH: Root login disabled
- UFW: Enabled, SSH only

The system reboots automatically. Reconnect at the static IP:
```bash
ssh john@192.168.10.129
```

## 6. SSH Key Setup

From Mac:
```bash
ssh-copy-id john@192.168.10.129
```

Verify passwordless login:
```bash
ssh john@192.168.10.129 "echo 'Key auth works'"
```

## 7. NVIDIA GPU Driver

```bash
# Check recommended driver
sudo ubuntu-drivers devices

# Install server variant (headless, no desktop)
sudo ubuntu-drivers install --gpgpu

# Install nvidia-smi utility
sudo apt install -y nvidia-utils-570-server

# Reboot for driver to load
sudo reboot
```

After reboot, verify:
```bash
nvidia-smi
```

Expected output: RTX 2070 Super, Driver 570.x, CUDA 12.x, 8192 MiB.

## 8. Docker Engine

Run the install script from the repo:
```bash
# From Mac:
scp infrastructure/holygrail/docker/install-docker.sh john@192.168.10.129:~/

# On HOLYGRAIL:
sudo ~/install-docker.sh
```

Log out and back in for docker group, then verify:
```bash
docker run --rm hello-world
docker compose version
```

## 9. NVIDIA Container Toolkit

Run the install script:
```bash
# From Mac:
scp infrastructure/holygrail/gpu/install-nvidia-container-toolkit.sh john@192.168.10.129:~/

# On HOLYGRAIL:
sudo ~/install-nvidia-container-toolkit.sh
```

Verify GPU inside container:
```bash
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

## 10. Portainer CE

Deploy via Compose:
```bash
# From Mac:
scp infrastructure/holygrail/docker/portainer-compose.yml john@192.168.10.129:~/

# On HOLYGRAIL:
docker compose -f ~/portainer-compose.yml up -d

# Open firewall for Portainer (LAN only)
sudo ufw allow from 192.168.10.0/24 to any port 9443 proto tcp
```

Access at `https://192.168.10.129:9443` — accept the self-signed cert and create an admin account.

## 11. SSH Hardening (Key-Only)

After confirming SSH key auth works:
```bash
# From Mac:
scp infrastructure/holygrail/harden-ssh.sh john@192.168.10.129:~/

# On HOLYGRAIL:
sudo ~/harden-ssh.sh
```

Verify password auth is rejected:
```bash
ssh -o PubkeyAuthentication=no john@192.168.10.129
# Should fail with "Permission denied (publickey)"
```

## 12. Passwordless Sudo (Optional)

For automated management via scripts:
```bash
echo "john ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/john
sudo chmod 440 /etc/sudoers.d/john
```

## 13. Verification

Run the full verification scripts:
```bash
sudo ~/verify-install.sh       # F1.1: OS, network, SSH, firewall
sudo ~/verify-docker-gpu.sh    # F1.2: Docker, GPU, Portainer
```

Both should report all checks PASSED.

---

## Final State

| Component | Value |
| --------- | ----- |
| IP | 192.168.10.129 (static) |
| OS | Ubuntu Server 24.04 LTS |
| Hostname | holygrail |
| Interface | enp7s0 |
| GPU | RTX 2070 Super, Driver 570.211.01, CUDA 12.8 |
| Docker | 29.4.0 + Compose 5.1.1 |
| Container Toolkit | nvidia-container-toolkit 1.19.0 |
| Portainer | CE latest, HTTPS :9443 |
| SSH | Key-only (password disabled) |
| Firewall | UFW: SSH (22) + Portainer (9443 from LAN) |
| DNS | Pi-hole (192.168.10.150) + 8.8.8.8 fallback |
| Timezone | America/Denver |
