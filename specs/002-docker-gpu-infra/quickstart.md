# Quickstart: Docker & GPU Infrastructure

**Branch**: `002-docker-gpu-infra` | **Date**: 2026-04-07

> Step-by-step execution guide for installing Docker, NVIDIA drivers, GPU container toolkit, and Portainer on HOLYGRAIL.

## Prerequisites

- [ ] F1.1 complete — HOLYGRAIL running Ubuntu Server 24.04 LTS at 192.168.10.129
- [ ] SSH access working: `ssh holygrail`
- [ ] Internet access working (DNS via Pi-hole + 8.8.8.8 fallback)
- [ ] RTX 2070 Super physically installed

## Step 1: Install NVIDIA GPU Driver (on HOLYGRAIL)

```bash
ssh holygrail
```

1. Check which driver is recommended:
   ```bash
   sudo ubuntu-drivers devices
   ```
2. Install the recommended server driver:
   ```bash
   sudo ubuntu-drivers install --gpgpu
   ```
   (Or explicitly: `sudo apt install -y nvidia-driver-560-server` — use the version reported above)
3. Reboot:
   ```bash
   sudo reboot
   ```
4. Reconnect and verify:
   ```bash
   ssh holygrail
   nvidia-smi
   ```
   Should show RTX 2070 Super with driver version and CUDA version.

## Step 2: Install Docker Engine (on HOLYGRAIL)

1. Copy and run the install script:
   ```bash
   # From Mac:
   scp infrastructure/holygrail/docker/install-docker.sh john@holygrail:~/
   ssh holygrail "chmod +x ~/install-docker.sh && sudo ~/install-docker.sh"
   ```

2. Log out and back in (for docker group):
   ```bash
   ssh holygrail
   ```

3. Verify Docker works without sudo:
   ```bash
   docker run --rm hello-world
   docker compose version
   ```

## Step 3: Install NVIDIA Container Toolkit (on HOLYGRAIL)

1. Copy and run the install script:
   ```bash
   # From Mac:
   scp infrastructure/holygrail/gpu/install-nvidia-container-toolkit.sh john@holygrail:~/
   ssh holygrail "chmod +x ~/install-nvidia-container-toolkit.sh && sudo ~/install-nvidia-container-toolkit.sh"
   ```

2. Test GPU inside a container:
   ```bash
   docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
   ```
   Should show the same RTX 2070 Super output as host `nvidia-smi`.

## Step 4: Deploy Portainer CE (on HOLYGRAIL)

1. Copy the Compose file and deploy:
   ```bash
   # From Mac:
   scp infrastructure/holygrail/docker/portainer-compose.yml john@holygrail:~/
   ssh holygrail "cd ~ && docker compose -f portainer-compose.yml up -d"
   ```

2. Open UFW port for Portainer:
   ```bash
   ssh holygrail "sudo ufw allow from 192.168.10.0/24 to any port 9443 proto tcp"
   ```

3. Access Portainer from Mac browser:
   ```
   https://192.168.10.129:9443
   ```
   Accept the self-signed certificate warning. Create an admin account on first visit.

## Step 5: Run Verification Script (on HOLYGRAIL)

```bash
# From Mac:
scp infrastructure/holygrail/verify-docker-gpu.sh john@holygrail:~/
ssh holygrail "chmod +x ~/verify-docker-gpu.sh && sudo ~/verify-docker-gpu.sh"
```

All checks should PASS.

## Step 6: Reboot and Verify Persistence

```bash
ssh holygrail "sudo reboot"
# Wait 60 seconds
ssh holygrail
nvidia-smi
docker ps  # Portainer should be running
```

Verify Portainer is accessible at `https://192.168.10.129:9443` from Mac.

## Post-Setup

- Commit all scripts and configs to repo on the `002-docker-gpu-infra` branch
- Mark F1.2 as complete in `docs/PROJECT-PLAN.md`
- Proceed to Phase 2 (service migration) or Phase 3 (Ollama & AI)
