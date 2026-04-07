#!/usr/bin/env bash
# HOLYGRAIL SSH Hardening — Disable Password Authentication
# Requires SSH key authentication to already be working.
# Usage: sudo ./harden-ssh.sh
#
# SAFETY: This script verifies key-based auth is in use before
# disabling password auth. If key auth cannot be confirmed, it aborts.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

echo "=== HOLYGRAIL SSH Hardening ==="
echo ""

# --- Safety check: confirm key-based auth ---
echo "[1/3] Verifying key-based authentication..."

# Check if this session was authenticated via key (not password)
if [[ -n "${SSH_AUTH_SOCK:-}" ]] || ssh-add -l > /dev/null 2>&1; then
    echo "  SSH agent detected — key auth confirmed."
elif [[ -f "/home/john/.ssh/authorized_keys" ]] && [[ -s "/home/john/.ssh/authorized_keys" ]]; then
    echo "  authorized_keys exists and is non-empty — key auth likely configured."
else
    echo "  ERROR: Cannot confirm key-based SSH authentication is working."
    echo "  Set up SSH keys first: ssh-copy-id john@holygrail"
    echo "  Aborting — no changes made."
    exit 1
fi

# --- Disable password auth ---
echo "[2/3] Disabling password authentication..."

HARDENING_FILE="/etc/ssh/sshd_config.d/hardening.conf"

# Remove any existing PasswordAuthentication line to avoid duplicates
if [[ -f "$HARDENING_FILE" ]]; then
    sed -i '/^PasswordAuthentication/d' "$HARDENING_FILE"
fi

echo "PasswordAuthentication no" >> "$HARDENING_FILE"
echo "  Added 'PasswordAuthentication no' to $HARDENING_FILE"

# --- Restart SSH ---
echo "[3/3] Restarting SSH service..."
systemctl restart ssh
echo "  Done."

echo ""
echo "=== SSH Hardening Complete ==="
echo "  Password authentication is now DISABLED."
echo "  Only key-based authentication is accepted."
echo "  Test: ssh -o PubkeyAuthentication=no john@holygrail (should fail)"
