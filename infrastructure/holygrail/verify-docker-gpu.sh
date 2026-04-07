#!/usr/bin/env bash
# HOLYGRAIL Docker & GPU Infrastructure Verification
# Checks all F1.2 acceptance criteria.
# Usage: sudo ./verify-docker-gpu.sh

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"

    if [[ "$result" == "true" ]]; then
        echo "  [PASS] $name"
        ((PASS++))
    else
        echo "  [FAIL] $name"
        ((FAIL++))
    fi
}

echo "=== HOLYGRAIL Docker & GPU Verification ==="
echo ""

# --- GPU Driver ---
echo "GPU Driver:"

NVIDIA_SMI_OK="false"
if command -v nvidia-smi > /dev/null 2>&1 && nvidia-smi > /dev/null 2>&1; then
    NVIDIA_SMI_OK="true"
fi
check "nvidia-smi available and working" "$NVIDIA_SMI_OK"

GPU_MODEL_OK="false"
if nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | grep -qi "2070"; then
    GPU_MODEL_OK="true"
fi
check "RTX 2070 Super detected" "$GPU_MODEL_OK"

HEADLESS_OK="false"
if ! systemctl list-units --type=service 2>/dev/null | grep -qiE 'gdm|lightdm|sddm'; then
    HEADLESS_OK="true"
fi
check "No desktop environment (headless)" "$HEADLESS_OK"

DRIVER_BOOT_OK="false"
if /usr/sbin/lsmod | grep nvidia > /dev/null 2>&1; then
    DRIVER_BOOT_OK="true"
fi
check "NVIDIA kernel module loaded" "$DRIVER_BOOT_OK"

# --- Docker ---
echo "Docker:"

DOCKER_RUNNING_OK="false"
if systemctl is-active docker > /dev/null 2>&1; then
    DOCKER_RUNNING_OK="true"
fi
check "Docker service running" "$DOCKER_RUNNING_OK"

DOCKER_ENABLED_OK="false"
if systemctl is-enabled docker > /dev/null 2>&1; then
    DOCKER_ENABLED_OK="true"
fi
check "Docker enabled on boot" "$DOCKER_ENABLED_OK"

DOCKER_GROUP_OK="false"
if groups john 2>/dev/null | grep -qw docker; then
    DOCKER_GROUP_OK="true"
fi
check "'john' in docker group" "$DOCKER_GROUP_OK"

COMPOSE_OK="false"
if docker compose version > /dev/null 2>&1; then
    COMPOSE_OK="true"
fi
check "Docker Compose v2 available" "$COMPOSE_OK"

# --- NVIDIA Container Toolkit ---
echo "GPU Containers:"

NVIDIA_RUNTIME_OK="false"
if docker info 2>/dev/null | grep -qi "nvidia"; then
    NVIDIA_RUNTIME_OK="true"
fi
check "NVIDIA runtime registered in Docker" "$NVIDIA_RUNTIME_OK"

GPU_CONTAINER_OK="false"
if docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi > /dev/null 2>&1; then
    GPU_CONTAINER_OK="true"
fi
check "GPU visible inside container" "$GPU_CONTAINER_OK"

# --- Portainer ---
echo "Portainer:"

PORTAINER_RUNNING_OK="false"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "portainer"; then
    PORTAINER_RUNNING_OK="true"
fi
check "Portainer container running" "$PORTAINER_RUNNING_OK"

PORTAINER_PORT_OK="false"
if curl -sk --connect-timeout 5 https://localhost:9443 > /dev/null 2>&1; then
    PORTAINER_PORT_OK="true"
fi
check "Portainer HTTPS accessible on port 9443" "$PORTAINER_PORT_OK"

UFW_PORTAINER_OK="false"
if ufw status | grep -q "9443"; then
    UFW_PORTAINER_OK="true"
fi
check "UFW rule for port 9443" "$UFW_PORTAINER_OK"

# --- Summary ---
echo ""
TOTAL=$((PASS + FAIL))
echo "=== Results: $PASS/$TOTAL passed ==="

if [[ $FAIL -eq 0 ]]; then
    echo "All checks PASSED. Docker & GPU infrastructure is correctly configured."
    exit 0
else
    echo "$FAIL check(s) FAILED. Review output above."
    exit 1
fi
