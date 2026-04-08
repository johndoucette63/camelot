#!/bin/bash
# Verify HOLYGRAIL monitoring stack deployment
# Usage: bash scripts/verify-monitoring.sh [--reboot-test]
#
# Checks:
#   - All monitoring services respond on expected ports
#   - InfluxDB network_metrics database exists
#   - Smokeping targets are collecting data
#   - Grafana dashboards are provisioned
#
# --reboot-test: SSH reboot HOLYGRAIL, wait 3 min, re-verify (SC-006)

set -euo pipefail

HOLYGRAIL="192.168.10.129"
HOLYGRAIL_SSH="john@holygrail"
PASS=0
FAIL=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        green "  PASS: $desc"
        ((PASS++))
    else
        red "  FAIL: $desc"
        ((FAIL++))
    fi
}

run_checks() {
    echo "=== HOLYGRAIL Monitoring Verification ==="
    echo "Target: $HOLYGRAIL"
    echo ""

    echo "--- Service Health ---"
    check "Grafana responds on :3000" \
        curl -sf --max-time 5 "http://$HOLYGRAIL:3000/api/health"
    check "InfluxDB responds on :8086" \
        curl -sf --max-time 5 "http://$HOLYGRAIL:8086/ping"
    check "Smokeping responds on :8080" \
        curl -sf --max-time 5 -o /dev/null "http://$HOLYGRAIL:8080"

    echo ""
    echo "--- Data Pipeline ---"
    check "InfluxDB network_metrics database exists" \
        curl -sf --max-time 5 "http://$HOLYGRAIL:8086/query?q=SHOW+DATABASES" -G | grep -q network_metrics
    check "Smokeping measurement has data" \
        curl -sf --max-time 5 "http://$HOLYGRAIL:8086/query?db=network_metrics&q=SELECT+count(*)FROM+smokeping+WHERE+time+>+now()-1h" -G | grep -q count

    echo ""
    echo "--- Grafana Dashboards ---"
    check "Grafana has provisioned dashboards" \
        curl -sf --max-time 5 "http://$HOLYGRAIL:3000/api/search" | grep -q network-monitoring

    echo ""
    echo "--- Docker Containers ---"
    for container in influxdb grafana smokeping smokeping-exporter speedtest; do
        check "Container $container is running" \
            ssh -o ConnectTimeout=5 "$HOLYGRAIL_SSH" "docker inspect -f '{{.State.Running}}' $container 2>/dev/null | grep -q true"
    done

    echo ""
    echo "=== Results: $PASS passed, $FAIL failed ==="
    return $FAIL
}

# Main
if [[ "${1:-}" == "--reboot-test" ]]; then
    echo "=== SC-006: Reboot Recovery Test ==="
    echo "Rebooting HOLYGRAIL..."
    ssh "$HOLYGRAIL_SSH" "sudo reboot" 2>/dev/null || true
    echo "Waiting 180 seconds for recovery..."
    sleep 180
    echo "Re-running verification..."
    echo ""
    run_checks
else
    run_checks
fi
