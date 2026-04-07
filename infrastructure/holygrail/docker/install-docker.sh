#!/usr/bin/env bash
# HOLYGRAIL Docker Engine Installation
# Installs Docker Engine, CLI, Compose v2, and buildx from the official Docker apt repo.
# Usage: sudo ./install-docker.sh
#
# This script is idempotent — safe to re-run.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

echo "=== HOLYGRAIL Docker Engine Installation ==="
echo ""

# --- Remove conflicting packages ---
echo "[1/5] Removing conflicting packages..."
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
    apt-get remove -y "$pkg" 2>/dev/null || true
done
echo "  Done."

# --- Install prerequisites ---
echo "[2/5] Installing prerequisites..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl
echo "  Done."

# --- Add Docker GPG key and apt source ---
echo "[3/5] Adding Docker repository..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
echo "  Done."

# --- Install Docker Engine ---
echo "[4/5] Installing Docker Engine + Compose..."
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
echo "  Done."

# --- Add john to docker group ---
echo "[5/5] Adding 'john' to docker group..."
if ! groups john 2>/dev/null | grep -qw docker; then
    usermod -aG docker john
    echo "  Added. Log out and back in for group change to take effect."
else
    echo "  Already in docker group."
fi

# --- Enable Docker on boot ---
systemctl enable docker
systemctl start docker

echo ""
echo "=== Docker Installation Complete ==="
echo "  Docker: $(docker --version)"
echo "  Compose: $(docker compose version)"
echo "  Note: 'john' must log out and back in for docker group access."
