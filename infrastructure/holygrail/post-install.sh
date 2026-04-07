#!/usr/bin/env bash
# HOLYGRAIL Post-Install Configuration Script
# Run after fresh Ubuntu Server 24.04 LTS install.
# Usage: sudo ./post-install.sh [TIMEZONE]
# Example: sudo ./post-install.sh America/Toronto
#
# This script is idempotent — safe to re-run.
# It will reboot the system at the end.

set -euo pipefail

# --- Preflight checks ---

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

TIMEZONE="${1:-}"
if [[ -z "$TIMEZONE" ]]; then
    echo "Usage: sudo $0 <TIMEZONE>"
    echo "Example: sudo $0 America/Toronto"
    echo ""
    echo "Available timezones: timedatectl list-timezones"
    exit 1
fi

# Validate timezone
if ! timedatectl list-timezones | grep -qx "$TIMEZONE"; then
    echo "ERROR: Invalid timezone '$TIMEZONE'."
    echo "Run 'timedatectl list-timezones' to see valid options."
    exit 1
fi

echo "=== HOLYGRAIL Post-Install Configuration ==="
echo ""

# --- Hostname ---

echo "[1/5] Setting hostname to 'holygrail'..."
hostnamectl set-hostname holygrail

# Ensure /etc/hosts has the hostname mapped
if ! grep -q "holygrail" /etc/hosts; then
    sed -i '/^127\.0\.1\.1/d' /etc/hosts
    echo "127.0.1.1    holygrail" >> /etc/hosts
fi
echo "  Done."

# --- Timezone ---

echo "[2/5] Setting timezone to '$TIMEZONE'..."
timedatectl set-timezone "$TIMEZONE"
echo "  Done."

# --- Static IP (Netplan) ---

echo "[3/5] Applying static IP configuration (192.168.10.129/24)..."

# The netplan config should be copied to ~/01-static-ip.yaml before running this script.
NETPLAN_SRC="$HOME/01-static-ip.yaml"
if [[ -n "${SUDO_USER:-}" ]]; then
    NETPLAN_SRC="/home/$SUDO_USER/01-static-ip.yaml"
fi

if [[ ! -f "$NETPLAN_SRC" ]]; then
    echo "  WARNING: $NETPLAN_SRC not found. Skipping netplan configuration."
    echo "  Copy 01-static-ip.yaml to the home directory and re-run."
else
    # Remove existing netplan configs and install ours
    rm -f /etc/netplan/*.yaml
    cp "$NETPLAN_SRC" /etc/netplan/01-static-ip.yaml
    chmod 600 /etc/netplan/01-static-ip.yaml
    netplan apply
    echo "  Done. Static IP: 192.168.10.129"
fi

# --- SSH Hardening ---

echo "[4/5] Hardening SSH (disabling root login)..."

SSHD_HARDENING="/etc/ssh/sshd_config.d/hardening.conf"
cat > "$SSHD_HARDENING" <<'SSHEOF'
# HOLYGRAIL SSH Hardening
# Managed by post-install.sh — do not edit manually.

# Explicitly deny root login (default is prohibit-password, but we want no access at all)
PermitRootLogin no
SSHEOF

chmod 644 "$SSHD_HARDENING"
systemctl restart ssh
echo "  Done. Root SSH login disabled."

# --- Firewall (UFW) ---

echo "[5/5] Configuring firewall (UFW — SSH only)..."

# Ensure UFW is installed
if ! command -v ufw > /dev/null 2>&1; then
    echo "  UFW not found. Installing..."
    apt-get update -qq
    apt-get install -y -qq ufw
fi

# Set defaults
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1

# Allow SSH before enabling (prevents lockout)
ufw allow ssh > /dev/null 2>&1

# Enable UFW (non-interactive)
echo "y" | ufw enable > /dev/null 2>&1
echo "  Done. UFW active — inbound SSH only."

# --- Summary ---

echo ""
echo "=== Configuration Complete ==="
echo "  Hostname:  $(hostname)"
echo "  Timezone:  $(timedatectl show --property=Timezone --value)"
echo "  Static IP: 192.168.10.129 (check with: ip addr)"
echo "  SSH:       Root login disabled, password + key auth enabled"
echo "  Firewall:  UFW active, SSH only"
echo ""
echo "System will reboot in 5 seconds..."
echo "Reconnect with: ssh john@192.168.10.129"
sleep 5
reboot
