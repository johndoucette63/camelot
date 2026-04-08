#!/bin/bash
# Verify Traefik hostname routing from Mac workstation
# Usage: bash scripts/verify-traefik-routes.sh
#
# Prerequisites:
#   - /etc/hosts entries configured (run scripts/setup-holygrail-dns.sh)
#   - Traefik running on HOLYGRAIL

set -euo pipefail

PASS=0
FAIL=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }

check_route() {
    local hostname="$1"
    local path="${2:-/}"
    local expected="${3:-200}"
    local status

    status=$(curl -sf --max-time 5 -o /dev/null -w '%{http_code}' "http://${hostname}${path}" 2>/dev/null || echo "000")

    if [[ "$status" == "$expected" ]]; then
        green "  PASS: $hostname -> HTTP $status"
        ((PASS++))
    else
        red "  FAIL: $hostname -> HTTP $status (expected $expected)"
        ((FAIL++))
    fi
}

echo "=== Traefik Route Verification ==="
echo ""

# Check DNS resolution first
echo "--- DNS Resolution ---"
for hostname in grafana.holygrail smokeping.holygrail plex.holygrail portainer.holygrail traefik.holygrail; do
    if host "$hostname" >/dev/null 2>&1 || ping -c1 -W1 "$hostname" >/dev/null 2>&1; then
        green "  PASS: $hostname resolves"
        ((PASS++))
    else
        red "  FAIL: $hostname does not resolve (check /etc/hosts)"
        ((FAIL++))
    fi
done

echo ""
echo "--- HTTP Routes ---"
check_route "grafana.holygrail" "/api/health"
check_route "smokeping.holygrail" "/"
check_route "plex.holygrail" "/identity"
check_route "portainer.holygrail" "/"
check_route "traefik.holygrail" "/api/overview"

echo ""
echo "--- Traefik Dashboard ---"
check_route "traefik.holygrail" "/api/http/routers"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
