#!/usr/bin/env bash
# HOLYGRAIL Installation Verification Script
# Checks all acceptance criteria from the F1.1 specification.
# Usage: sudo ./verify-install.sh
#
# Outputs PASS/FAIL for each check with a final summary.

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

echo "=== HOLYGRAIL Installation Verification ==="
echo ""

# --- FR-009: Hostname ---
echo "Hostname:"
HOSTNAME_OK="false"
if [[ "$(hostname)" == "holygrail" ]]; then
    HOSTNAME_OK="true"
fi
check "Hostname is 'holygrail'" "$HOSTNAME_OK"

# --- FR-010: Static IP ---
echo "Network:"
STATIC_IP_OK="false"
if ip addr show | grep -q "192.168.10.129/24"; then
    STATIC_IP_OK="true"
fi
check "Static IP is 192.168.10.129/24" "$STATIC_IP_OK"

# --- FR-012: DNS via Pi-hole ---
DNS_OK="false"
# Check netplan or resolved config for Pi-hole DNS
if resolvectl status 2>/dev/null | grep -q "192.168.10.150"; then
    DNS_OK="true"
elif grep -q "192.168.10.150" /etc/netplan/*.yaml 2>/dev/null; then
    DNS_OK="true"
fi
check "DNS configured to use Pi-hole (192.168.10.150)" "$DNS_OK"

# --- FR-011: Timezone ---
echo "System:"
TZ_OK="false"
CURRENT_TZ=$(timedatectl show --property=Timezone --value 2>/dev/null)
if [[ -n "$CURRENT_TZ" && "$CURRENT_TZ" != "Etc/UTC" ]]; then
    TZ_OK="true"
fi
check "Timezone is set ($CURRENT_TZ)" "$TZ_OK"

# --- FR-003: Ubuntu Server 24.04 LTS ---
OS_OK="false"
if grep -q "24.04" /etc/os-release 2>/dev/null; then
    OS_OK="true"
fi
check "Ubuntu Server 24.04 LTS installed" "$OS_OK"

# --- FR-004: OpenSSH accessible ---
echo "SSH:"
SSH_OK="false"
if systemctl is-active ssh > /dev/null 2>&1; then
    SSH_OK="true"
fi
check "OpenSSH server is running" "$SSH_OK"

# --- FR-005: Root SSH disabled ---
ROOT_SSH_OK="false"
# Check both the drop-in and effective config
if sshd -T 2>/dev/null | grep -qi "permitrootlogin no"; then
    ROOT_SSH_OK="true"
elif grep -q "PermitRootLogin no" /etc/ssh/sshd_config.d/hardening.conf 2>/dev/null; then
    ROOT_SSH_OK="true"
fi
check "Root SSH login disabled (PermitRootLogin no)" "$ROOT_SSH_OK"

# --- FR-007: Password authentication enabled ---
PASS_AUTH_OK="false"
# Check effective sshd config — PasswordAuthentication defaults to yes
PASS_AUTH_VALUE=$(sshd -T 2>/dev/null | grep -i "passwordauthentication" | awk '{print $2}')
if [[ "$PASS_AUTH_VALUE" == "yes" ]]; then
    PASS_AUTH_OK="true"
fi
check "Password authentication enabled (FR-007)" "$PASS_AUTH_OK"

# --- FR-006: john user with sudo ---
echo "User:"
JOHN_OK="false"
if id john > /dev/null 2>&1; then
    JOHN_OK="true"
fi
check "User 'john' exists" "$JOHN_OK"

SUDO_OK="false"
if groups john 2>/dev/null | grep -qw "sudo"; then
    SUDO_OK="true"
fi
check "User 'john' has sudo privileges" "$SUDO_OK"

# --- FR-008: Firewall (UFW) ---
echo "Firewall:"
UFW_ACTIVE_OK="false"
if ufw status | grep -q "Status: active"; then
    UFW_ACTIVE_OK="true"
fi
check "UFW is active" "$UFW_ACTIVE_OK"

UFW_SSH_OK="false"
if ufw status | grep -q "22/tcp.*ALLOW"; then
    UFW_SSH_OK="true"
fi
check "UFW allows SSH (port 22)" "$UFW_SSH_OK"

# Check that only SSH is allowed (no other ALLOW rules besides SSH)
UFW_ONLY_SSH_OK="false"
ALLOW_COUNT=$(ufw status | grep "ALLOW" | grep -cv "22/tcp" || true)
if [[ "$ALLOW_COUNT" -eq 0 ]]; then
    UFW_ONLY_SSH_OK="true"
fi
check "UFW allows SSH only (no other inbound rules)" "$UFW_ONLY_SSH_OK"

# --- Summary ---
echo ""
TOTAL=$((PASS + FAIL))
echo "=== Results: $PASS/$TOTAL passed ==="

if [[ $FAIL -eq 0 ]]; then
    echo "All checks PASSED. HOLYGRAIL is correctly configured."
    exit 0
else
    echo "$FAIL check(s) FAILED. Review output above."
    exit 1
fi
