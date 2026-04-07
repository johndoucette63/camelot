#!/bin/bash
# Remote status checker for all Camelot devices
# Run from Mac: bash scripts/pi-status.sh [holygrail|torrentbox|nas|mediaserver|all]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Device definitions: name|host|user
DEVICES=(
    "HOLYGRAIL|192.168.10.129|john"
    "Torrentbox|192.168.10.141|john"
    "NAS|192.168.10.105|pi"
    "Pi-hole DNS|192.168.10.150|pi"
)

SSH_OPTS="-o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o BatchMode=yes"

check_host() {
    local name="$1"
    local host="$2"
    local user="$3"

    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  ${name} (${host})${NC}"
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Check if host is reachable
    if ! ping -c 1 -W 2 "$host" > /dev/null 2>&1; then
        echo -e "  Status: ${RED}OFFLINE${NC}"
        echo ""
        return 1
    fi
    echo -e "  Status: ${GREEN}ONLINE${NC}"

    # Run all status commands in one SSH session
    local status_script='
        echo "::UPTIME::"
        uptime -p 2>/dev/null || uptime | sed "s/.*up/up/"

        echo "::HOSTNAME::"
        hostname

        echo "::OS::"
        cat /etc/os-release 2>/dev/null | grep -E "^PRETTY_NAME=" | cut -d= -f2 | tr -d \"

        echo "::CPU_TEMP::"
        if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
            awk "{printf \"%.1f°C\", \$1/1000}" /sys/class/thermal/thermal_zone0/temp
        else
            echo "N/A"
        fi

        echo "::MEMORY::"
        free -h | awk "/^Mem:/ {printf \"%s / %s (%s used)\n\", \$3, \$2, \$3}"

        echo "::DISK::"
        df -h --output=source,size,used,avail,pcent,target 2>/dev/null | grep -vE "^Filesystem|tmpfs|udev|overlay" | head -10

        echo "::DOCKER::"
        if command -v docker &>/dev/null; then
            docker ps --format "{{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Docker not accessible"
        else
            echo "Not installed"
        fi

        echo "::MOUNTS::"
        mount | grep cifs 2>/dev/null || echo "No SMB mounts"

        echo "::GPU::"
        if command -v nvidia-smi &>/dev/null; then
            nvidia-smi --query-gpu=name,temperature.gpu,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo "N/A"
        else
            echo "N/A"
        fi

        echo "::UPDATES::"
        if command -v apt &>/dev/null; then
            apt list --upgradable 2>/dev/null | grep -c upgradable || echo "0"
        else
            echo "N/A"
        fi
    '

    local output
    if ! output=$(ssh $SSH_OPTS "${user}@${host}" "$status_script" 2>/dev/null); then
        echo -e "  ${RED}SSH connection failed${NC}"
        echo ""
        return 1
    fi

    # Parse sections
    local section=""
    while IFS= read -r line; do
        case "$line" in
            "::UPTIME::")   section="uptime"; continue ;;
            "::HOSTNAME::") section="hostname"; continue ;;
            "::OS::")       section="os"; continue ;;
            "::CPU_TEMP::") section="temp"; continue ;;
            "::MEMORY::")   section="memory"; continue ;;
            "::DISK::")     section="disk"; continue ;;
            "::GPU::")      section="gpu"; continue ;;
            "::DOCKER::")   section="docker"; continue ;;
            "::MOUNTS::")   section="mounts"; continue ;;
            "::UPDATES::")  section="updates"; continue ;;
        esac

        [ -z "$line" ] && continue

        case "$section" in
            uptime)
                echo -e "  Uptime: ${CYAN}${line}${NC}"
                ;;
            os)
                echo -e "  OS: ${line}"
                ;;
            temp)
                if [ "$line" = "N/A" ]; then
                    echo -e "  CPU Temp: N/A"
                else
                    local temp_num
                    temp_num=$(echo "$line" | grep -oE '[0-9.]+' | head -1 || true)
                    if [ -n "$temp_num" ]; then
                        if [ "$(echo "$temp_num > 70" | bc -l 2>/dev/null)" = "1" ]; then
                            echo -e "  CPU Temp: ${RED}${line}${NC}"
                        elif [ "$(echo "$temp_num > 55" | bc -l 2>/dev/null)" = "1" ]; then
                            echo -e "  CPU Temp: ${YELLOW}${line}${NC}"
                        else
                            echo -e "  CPU Temp: ${GREEN}${line}${NC}"
                        fi
                    else
                        echo -e "  CPU Temp: ${line}"
                    fi
                fi
                ;;
            gpu)
                if [ "$line" != "N/A" ]; then
                    # nvidia-smi CSV format: "name, temp, mem_used, mem_total, util"
                    local gpu_name gpu_temp gpu_mem_used gpu_mem_total gpu_util
                    gpu_name=$(echo "$line" | cut -d',' -f1 | xargs)
                    gpu_temp=$(echo "$line" | cut -d',' -f2 | xargs)
                    gpu_mem_used=$(echo "$line" | cut -d',' -f3 | xargs)
                    gpu_mem_total=$(echo "$line" | cut -d',' -f4 | xargs)
                    gpu_util=$(echo "$line" | cut -d',' -f5 | xargs)
                    # Color-code GPU temp: green <60, yellow 60-80, red >80
                    local gpu_temp_color="${GREEN}"
                    if [ -n "$gpu_temp" ] && [ "$gpu_temp" -gt 80 ] 2>/dev/null; then
                        gpu_temp_color="${RED}"
                    elif [ -n "$gpu_temp" ] && [ "$gpu_temp" -gt 60 ] 2>/dev/null; then
                        gpu_temp_color="${YELLOW}"
                    fi
                    echo -e "  GPU: ${CYAN}${gpu_name}${NC}"
                    echo -e "  GPU Temp: ${gpu_temp_color}${gpu_temp}°C${NC}"
                    echo -e "  GPU Memory: ${gpu_mem_used}MiB / ${gpu_mem_total}MiB"
                    echo -e "  GPU Util: ${gpu_util}%"
                fi
                ;;
            memory)
                echo -e "  Memory: ${line}"
                ;;
            disk)
                if [ "$section" = "disk" ]; then
                    # Color-code disk usage
                    local pct
                    pct=$(echo "$line" | awk '{print $5}' | tr -d '%')
                    if [ -n "$pct" ] && [ "$pct" -gt 90 ] 2>/dev/null; then
                        echo -e "  ${RED}${line}${NC}"
                    elif [ -n "$pct" ] && [ "$pct" -gt 75 ] 2>/dev/null; then
                        echo -e "  ${YELLOW}${line}${NC}"
                    else
                        echo -e "  ${line}"
                    fi
                fi
                ;;
            docker)
                if [ "$line" = "Not installed" ]; then
                    echo -e "  Docker: ${YELLOW}Not installed${NC}"
                elif [ "$line" = "Docker not accessible" ]; then
                    echo -e "  Docker: ${RED}Not accessible${NC}"
                else
                    local container_name status
                    container_name=$(echo "$line" | cut -f1)
                    status=$(echo "$line" | cut -f2)
                    if echo "$status" | grep -qi "up"; then
                        echo -e "  ${GREEN}●${NC} ${container_name} — ${status}"
                    else
                        echo -e "  ${RED}●${NC} ${container_name} — ${status}"
                    fi
                fi
                ;;
            mounts)
                if [ "$line" = "No SMB mounts" ]; then
                    echo -e "  SMB Mounts: ${YELLOW}None${NC}"
                else
                    local mount_target
                    mount_target=$(echo "$line" | awk '{print $3}')
                    echo -e "  SMB: ${mount_target}"
                fi
                ;;
            updates)
                if [ "$line" != "N/A" ] && [ "$line" -gt 0 ] 2>/dev/null; then
                    echo -e "  Updates: ${YELLOW}${line} packages available${NC}"
                else
                    echo -e "  Updates: ${GREEN}System up to date${NC}"
                fi
                ;;
        esac
    done <<< "$output"

    echo ""
}

# Main
target="${1:-all}"

echo -e "${BOLD}${CYAN}"
echo "  ┌──────────────────────────────────┐"
echo "  │   Camelot Infrastructure Status   │"
echo "  │   $(date '+%Y-%m-%d %H:%M:%S')          │"
echo "  └──────────────────────────────────┘"
echo -e "${NC}"

case "$target" in
    all)
        for device in "${DEVICES[@]}"; do
            IFS='|' read -r name host user <<< "$device"
            check_host "$name" "$host" "$user"
        done
        ;;
    holygrail)
        check_host "HOLYGRAIL" "192.168.10.129" "john"
        ;;
    torrentbox)
        check_host "Torrentbox" "192.168.10.141" "john"
        ;;
    nas)
        check_host "NAS" "192.168.10.105" "pi"
        ;;
    mediaserver|media|pihole)
        check_host "Pi-hole DNS" "192.168.10.150" "pi"
        ;;
    *)
        echo "Usage: $0 [all|holygrail|torrentbox|nas|mediaserver|pihole]"
        exit 1
        ;;
esac
