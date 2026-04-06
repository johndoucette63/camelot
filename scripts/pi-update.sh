#!/bin/bash
# Remote updater for Raspberry Pi devices
# Run from Mac: bash scripts/pi-update.sh [torrentbox|nas|mediaserver|all] [--os|--docker|--both]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"

log_info()  { echo -e "  ${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "  ${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "  ${YELLOW}[WARN]${NC}  $*"; }
log_err()   { echo -e "  ${RED}[ERROR]${NC} $*"; }

update_os() {
    local name="$1" host="$2" user="$3"

    echo -e "\n${BOLD}${CYAN}  OS Update: ${name} (${host})${NC}"

    if ! ping -c 1 -W 2 "$host" > /dev/null 2>&1; then
        log_err "${name} is offline — skipping"
        return 1
    fi

    log_info "Checking for updates..."
    local update_count
    update_count=$(ssh $SSH_OPTS "${user}@${host}" "sudo apt update -qq 2>/dev/null && apt list --upgradable 2>/dev/null | grep -c upgradable || echo 0")

    if [ "$update_count" -eq 0 ] 2>/dev/null; then
        log_ok "System is up to date"
        return 0
    fi

    log_warn "${update_count} packages to upgrade"

    # Show what will be upgraded
    ssh $SSH_OPTS "${user}@${host}" "apt list --upgradable 2>/dev/null" | grep -v "^Listing" | while read -r line; do
        echo -e "    ${line}"
    done

    echo ""
    read -r -p "  Proceed with upgrade on ${name}? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_info "Skipped"
        return 0
    fi

    log_info "Running apt upgrade..."
    ssh -t $SSH_OPTS "${user}@${host}" "sudo apt upgrade -y 2>&1" | while read -r line; do
        echo -e "    ${line}"
    done

    # Check if reboot is required
    local needs_reboot
    needs_reboot=$(ssh $SSH_OPTS "${user}@${host}" "[ -f /var/run/reboot-required ] && echo yes || echo no")
    if [ "$needs_reboot" = "yes" ]; then
        log_warn "Reboot required!"
        read -r -p "  Reboot ${name} now? [y/N] " reboot_confirm
        if [[ "$reboot_confirm" =~ ^[Yy]$ ]]; then
            log_info "Rebooting..."
            ssh $SSH_OPTS "${user}@${host}" "sudo reboot" 2>/dev/null || true
            log_ok "Reboot initiated"
        fi
    else
        log_ok "OS update complete — no reboot required"
    fi
}

update_docker() {
    local name="$1" host="$2" user="$3"

    echo -e "\n${BOLD}${CYAN}  Docker Update: ${name} (${host})${NC}"

    if ! ping -c 1 -W 2 "$host" > /dev/null 2>&1; then
        log_err "${name} is offline — skipping"
        return 1
    fi

    # Check if Docker is installed
    if ! ssh $SSH_OPTS "${user}@${host}" "command -v docker" > /dev/null 2>&1; then
        log_warn "Docker not installed on ${name}"
        return 0
    fi

    # Find docker-compose files
    local compose_dirs
    compose_dirs=$(ssh $SSH_OPTS "${user}@${host}" "find ~/docker /home/*/docker -maxdepth 1 -name 'docker-compose.yml' -o -name 'compose.yml' 2>/dev/null | xargs -I{} dirname {}" | sort -u)

    if [ -z "$compose_dirs" ]; then
        log_warn "No docker-compose files found"
        return 0
    fi

    for dir in $compose_dirs; do
        log_info "Compose project: ${dir}"

        # Show current containers
        log_info "Current containers:"
        ssh $SSH_OPTS "${user}@${host}" "cd ${dir} && docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}'" 2>/dev/null | while read -r line; do
            echo -e "    ${line}"
        done

        echo ""
        log_info "Pulling latest images..."
        local pull_output
        pull_output=$(ssh $SSH_OPTS "${user}@${host}" "cd ${dir} && docker compose pull 2>&1")

        # Check if any images were updated
        if echo "$pull_output" | grep -q "Downloaded newer image\|Pull complete"; then
            log_warn "New images available"
            echo "$pull_output" | grep -E "Downloaded|Pulling|Status" | while read -r line; do
                echo -e "    ${line}"
            done

            echo ""
            read -r -p "  Recreate containers with new images? [y/N] " confirm
            if [[ "$confirm" =~ ^[Yy]$ ]]; then
                log_info "Recreating containers..."
                ssh $SSH_OPTS "${user}@${host}" "cd ${dir} && docker compose up -d 2>&1" | while read -r line; do
                    echo -e "    ${line}"
                done
                log_ok "Containers updated"
            else
                log_info "Skipped — images pulled but containers not recreated"
            fi
        else
            log_ok "All images up to date"
        fi

        # Clean up old images
        local dangling
        dangling=$(ssh $SSH_OPTS "${user}@${host}" "docker images -f dangling=true -q 2>/dev/null | wc -l | tr -d ' '")
        if [ "$dangling" -gt 0 ] 2>/dev/null; then
            log_info "Cleaning up ${dangling} dangling images..."
            ssh $SSH_OPTS "${user}@${host}" "docker image prune -f" > /dev/null 2>&1
            log_ok "Cleaned"
        fi
    done
}

# Device definitions
declare -A HOSTS=(
    [torrentbox]="Torrentbox|192.168.10.141|john"
    [nas]="NAS|192.168.10.105|pi"
    [mediaserver]="Media Server|192.168.10.150|pi"
)

usage() {
    echo "Usage: $0 [target] [mode]"
    echo ""
    echo "Targets:  all, torrentbox, nas, mediaserver"
    echo "Modes:    --os      OS packages only (apt upgrade)"
    echo "          --docker  Docker images only"
    echo "          --both    OS + Docker (default)"
    echo ""
    echo "Examples:"
    echo "  $0 all              # Update everything on all devices"
    echo "  $0 torrentbox --docker  # Update Docker on Torrentbox only"
    echo "  $0 nas --os         # Update OS on NAS only"
}

run_updates() {
    local name host user
    IFS='|' read -r name host user <<< "$1"
    local mode="$2"

    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  ${name} (${host})${NC}"
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    case "$mode" in
        os)     update_os "$name" "$host" "$user" ;;
        docker) update_docker "$name" "$host" "$user" ;;
        both)
            update_os "$name" "$host" "$user"
            update_docker "$name" "$host" "$user"
            ;;
    esac
}

# Parse arguments
target="${1:-all}"
mode="both"
case "${2:-}" in
    --os)     mode="os" ;;
    --docker) mode="docker" ;;
    --both)   mode="both" ;;
    --help|-h) usage; exit 0 ;;
    "") ;;
    *) echo "Unknown mode: $2"; usage; exit 1 ;;
esac

echo -e "${BOLD}${CYAN}"
echo "  ┌──────────────────────────────────┐"
echo "  │   Pi Infrastructure Updater      │"
echo "  │   $(date '+%Y-%m-%d %H:%M:%S')          │"
echo "  │   Mode: ${mode}                       │"
echo "  └──────────────────────────────────┘"
echo -e "${NC}"

case "$target" in
    all)
        for key in torrentbox nas mediaserver; do
            run_updates "${HOSTS[$key]}" "$mode"
        done
        ;;
    torrentbox|nas|mediaserver)
        run_updates "${HOSTS[$target]}" "$mode"
        ;;
    *)
        echo "Unknown target: $target"
        usage
        exit 1
        ;;
esac

echo -e "\n${GREEN}${BOLD}  Done.${NC}"
