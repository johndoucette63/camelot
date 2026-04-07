#!/usr/bin/env bash
# HOLYGRAIL Plex Media Server Verification
# Checks all F2.1 acceptance criteria.
# Usage: sudo ./verify-plex.sh

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

echo "=== HOLYGRAIL Plex Media Server Verification ==="
echo ""

# --- Plex Container ---
echo "Plex Container:"

PLEX_RUNNING_OK="false"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^plex$"; then
    PLEX_RUNNING_OK="true"
fi
check "Plex container running" "$PLEX_RUNNING_OK"

PLEX_RESTART_OK="false"
if docker inspect plex --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null | grep -q "unless-stopped"; then
    PLEX_RESTART_OK="true"
fi
check "Restart policy: unless-stopped" "$PLEX_RESTART_OK"

PLEX_HEALTHY_OK="false"
HEALTH_STATUS=$(docker inspect plex --format '{{.State.Health.Status}}' 2>/dev/null || echo "none")
if [[ "$HEALTH_STATUS" == "healthy" ]]; then
    PLEX_HEALTHY_OK="true"
fi
check "Healthcheck: healthy (status: $HEALTH_STATUS)" "$PLEX_HEALTHY_OK"

# --- GPU Access ---
echo "GPU Access:"

GPU_IN_CONTAINER_OK="false"
if docker exec plex nvidia-smi > /dev/null 2>&1; then
    GPU_IN_CONTAINER_OK="true"
fi
check "nvidia-smi works inside Plex container" "$GPU_IN_CONTAINER_OK"

GPU_MODEL_OK="false"
if docker exec plex nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | grep -qi "2070"; then
    GPU_MODEL_OK="true"
fi
check "RTX 2070 Super visible in container" "$GPU_MODEL_OK"

# --- Web UI ---
echo "Web UI:"

PLEX_WEB_OK="false"
if curl -sf --connect-timeout 5 "http://localhost:32400/identity" > /dev/null 2>&1; then
    PLEX_WEB_OK="true"
fi
check "Plex web UI accessible on port 32400" "$PLEX_WEB_OK"

# --- NAS Mounts ---
echo "NAS Mounts:"

MOVIES_OK="false"
if mountpoint -q /mnt/nas/movies 2>/dev/null; then
    MOVIES_OK="true"
fi
check "/mnt/nas/movies mounted" "$MOVIES_OK"

TV_OK="false"
if mountpoint -q /mnt/nas/tv 2>/dev/null; then
    TV_OK="true"
fi
check "/mnt/nas/tv mounted" "$TV_OK"

MUSIC_OK="false"
if mountpoint -q /mnt/nas/music 2>/dev/null; then
    MUSIC_OK="true"
fi
check "/mnt/nas/music mounted" "$MUSIC_OK"

# --- Firewall ---
echo "Firewall:"

UFW_PLEX_OK="false"
if ufw status | grep -q "32400"; then
    UFW_PLEX_OK="true"
fi
check "UFW rule for port 32400" "$UFW_PLEX_OK"

# --- Pi-hole DNS ---
echo "Pi-hole (Media Server Pi):"

PIHOLE_OK="false"
if timeout 3 bash -c 'echo >/dev/tcp/192.168.10.150/53' 2>/dev/null; then
    PIHOLE_OK="true"
fi
check "Pi-hole DNS listening on port 53 (192.168.10.150)" "$PIHOLE_OK"

# --- Summary ---
echo ""
TOTAL=$((PASS + FAIL))
echo "=== Results: $PASS/$TOTAL passed ==="

if [[ $FAIL -eq 0 ]]; then
    echo "All checks PASSED. Plex Media Server is correctly configured."
    exit 0
else
    echo "$FAIL check(s) FAILED. Review output above."
    exit 1
fi
