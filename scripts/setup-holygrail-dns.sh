#!/bin/bash
# Setup /etc/hosts entries for HOLYGRAIL services (Mac workstation)
# Usage: sudo bash scripts/setup-holygrail-dns.sh

set -euo pipefail

HOLYGRAIL_IP="192.168.10.129"
HOSTS_FILE="/etc/hosts"
MARKER="# HOLYGRAIL services (Camelot)"

HOSTNAMES=(
    "grafana.holygrail"
    "smokeping.holygrail"
    "plex.holygrail"
    "portainer.holygrail"
    "traefik.holygrail"
    "ollama.holygrail"
)

# Check for root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run with sudo:"
    echo "  sudo bash $0"
    exit 1
fi

# Check if entries already exist
if grep -q "$MARKER" "$HOSTS_FILE" 2>/dev/null; then
    echo "HOLYGRAIL DNS entries already exist in $HOSTS_FILE"
    echo "Current entries:"
    sed -n "/$MARKER/,/^$/p" "$HOSTS_FILE"
    echo ""
    echo "To update, remove the existing block first, then re-run this script."
    exit 0
fi

# Append entries
echo "" >> "$HOSTS_FILE"
echo "$MARKER" >> "$HOSTS_FILE"
for hostname in "${HOSTNAMES[@]}"; do
    echo "$HOLYGRAIL_IP  $hostname" >> "$HOSTS_FILE"
done

echo "Added ${#HOSTNAMES[@]} hostname entries to $HOSTS_FILE:"
for hostname in "${HOSTNAMES[@]}"; do
    echo "  $HOLYGRAIL_IP  $hostname"
done
echo ""
echo "Verify with: ping -c1 grafana.holygrail"
