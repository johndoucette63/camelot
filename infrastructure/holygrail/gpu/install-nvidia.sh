#!/usr/bin/env bash
# HOLYGRAIL NVIDIA GPU Driver Installation
# Installs the recommended server-variant NVIDIA driver (headless, no desktop).
# Usage: sudo ./install-nvidia.sh
#
# This script is idempotent — safe to re-run.
# Requires a reboot after installation.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

echo "=== HOLYGRAIL NVIDIA Driver Installation ==="
echo ""

# --- Check for GPU hardware ---
echo "[1/4] Detecting GPU hardware..."
if ! lspci | grep -i nvidia > /dev/null 2>&1; then
    echo "  ERROR: No NVIDIA GPU detected via lspci."
    echo "  Verify the RTX 2070 Super is physically installed."
    exit 1
fi
echo "  Found: $(lspci | grep -i nvidia | head -1)"

# --- Check recommended driver ---
echo "[2/4] Checking recommended driver..."
apt-get update -qq
apt-get install -y -qq ubuntu-drivers-common

echo "  Available drivers:"
ubuntu-drivers devices 2>/dev/null || true
echo ""

# --- Install driver ---
echo "[3/4] Installing recommended NVIDIA server driver..."
ubuntu-drivers install --gpgpu

# --- Verify no desktop environment ---
echo "[4/4] Verifying headless operation..."
if systemctl list-units --type=service 2>/dev/null | grep -qiE 'gdm|lightdm|sddm'; then
    echo "  WARNING: A display manager was detected. This should be a headless server."
else
    echo "  Confirmed: No display manager running (headless)."
fi

echo ""
echo "=== NVIDIA Driver Installation Complete ==="
echo "  A reboot is required for the driver to load."
echo "  After reboot, verify with: nvidia-smi"
echo ""
echo "Reboot now? (y/N)"
read -r REPLY
if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    reboot
fi
