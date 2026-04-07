#!/usr/bin/env bash
# HOLYGRAIL NVIDIA Container Toolkit Installation
# Enables GPU passthrough into Docker containers.
# Usage: sudo ./install-nvidia-container-toolkit.sh
#
# Prerequisites: NVIDIA driver installed (nvidia-smi works), Docker Engine installed.
# This script is idempotent — safe to re-run.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

echo "=== HOLYGRAIL NVIDIA Container Toolkit Installation ==="
echo ""

# --- Preflight checks ---
echo "[1/4] Checking prerequisites..."

if ! command -v nvidia-smi > /dev/null 2>&1; then
    echo "  ERROR: nvidia-smi not found. Install NVIDIA drivers first (install-nvidia.sh)."
    exit 1
fi
echo "  NVIDIA driver: OK ($(nvidia-smi --query-gpu=driver_version --format=csv,noheader))"

if ! command -v docker > /dev/null 2>&1; then
    echo "  ERROR: Docker not found. Install Docker first (install-docker.sh)."
    exit 1
fi
echo "  Docker: OK ($(docker --version))"

# --- Add NVIDIA Container Toolkit repository ---
echo "[2/4] Adding NVIDIA Container Toolkit repository..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
echo "  Done."

# --- Install toolkit ---
echo "[3/4] Installing nvidia-container-toolkit..."
apt-get update -qq
apt-get install -y -qq nvidia-container-toolkit
echo "  Done."

# --- Configure Docker runtime ---
echo "[4/4] Configuring Docker nvidia runtime..."
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
echo "  Done. NVIDIA runtime registered in Docker."

echo ""
echo "=== NVIDIA Container Toolkit Installation Complete ==="
echo "  Test with: docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi"
