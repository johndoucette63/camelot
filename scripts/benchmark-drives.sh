#!/bin/bash
# Media Infrastructure Drive Benchmark Script
# Run this script on each Pi to benchmark local and network drives

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect OS
OS_TYPE=$(uname -s)

HOSTNAME=$(hostname)
DATE=$(date '+%Y-%m-%d %H:%M:%S')
RESULTS_FILE="/tmp/benchmark-results-${HOSTNAME}.txt"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Drive Benchmark - ${HOSTNAME}${NC}"
echo -e "${BLUE}  ${DATE}${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Initialize results file
echo "Drive Benchmark Results - ${HOSTNAME}" > "$RESULTS_FILE"
echo "Date: ${DATE}" >> "$RESULTS_FILE"
echo "========================================" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

parse_dd_speed() {
    # Parse dd output across Linux and macOS
    # Linux:  "536870912 bytes (537 MB, 512 MiB) copied, 1.234 s, 435 MB/s"
    # macOS:  "536870912 bytes transferred in 1.234 secs (435000000 bytes/sec)"
    local dd_output="$1"
    if echo "$dd_output" | grep -q "bytes/sec"; then
        # macOS format — convert bytes/sec to MB/s
        local bytes_sec
        bytes_sec=$(echo "$dd_output" | sed -n 's/.*(\([0-9]*\) bytes\/sec).*/\1/p')
        if [ -n "$bytes_sec" ]; then
            echo "scale=1; ${bytes_sec}/1048576" | bc 2>/dev/null
            return
        fi
    fi
    # Linux format
    echo "$dd_output" | grep -oE '[0-9.]+ [MG]B/s' | tail -1
}

clear_disk_cache() {
    if [ "$OS_TYPE" = "Darwin" ]; then
        sudo purge 2>/dev/null || true
    else
        sync
        echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null 2>&1 || true
    fi
}

get_fio_ioengine() {
    if [ "$OS_TYPE" = "Darwin" ]; then
        echo "posixaio"
    else
        echo "libaio"
    fi
}

benchmark_drive() {
    local path="$1"
    local name="$2"
    local testfile="${path}/benchmark_test_$$"

    echo -e "${YELLOW}Testing: ${name}${NC}"
    echo -e "${YELLOW}Path: ${path}${NC}"
    echo ""

    # Check if path exists and is writable
    if [ ! -d "$path" ]; then
        echo -e "${RED}  ERROR: Path does not exist${NC}"
        echo "${name}: PATH NOT FOUND" >> "$RESULTS_FILE"
        echo "" >> "$RESULTS_FILE"
        return
    fi

    if ! touch "${testfile}" 2>/dev/null; then
        echo -e "${RED}  ERROR: Path is not writable${NC}"
        echo "${name}: NOT WRITABLE" >> "$RESULTS_FILE"
        echo "" >> "$RESULTS_FILE"
        return
    fi
    rm -f "${testfile}"

    echo "${name} (${path})" >> "$RESULTS_FILE"
    echo "----------------------------------------" >> "$RESULTS_FILE"

    # Sequential Write Test (512MB)
    echo -e "  ${GREEN}Sequential Write (512MB)...${NC}"
    sync
    if [ "$OS_TYPE" = "Darwin" ]; then
        write_result=$(dd if=/dev/zero of="${testfile}" bs=1048576 count=512 2>&1 | tail -1)
    else
        write_result=$(dd if=/dev/zero of="${testfile}" bs=1M count=512 conv=fdatasync 2>&1 | tail -1)
    fi
    write_speed=$(parse_dd_speed "$write_result")
    if echo "$write_speed" | grep -qE '^[0-9]'; then
        write_speed="${write_speed} MB/s"
    fi
    echo -e "  Write Speed: ${BLUE}${write_speed}${NC}"
    echo "  Sequential Write: ${write_speed}" >> "$RESULTS_FILE"

    # Clear cache for accurate read test
    clear_disk_cache

    # Sequential Read Test
    echo -e "  ${GREEN}Sequential Read (512MB)...${NC}"
    read_result=$(dd if="${testfile}" of=/dev/null bs=1048576 2>&1 | tail -1)
    read_speed=$(parse_dd_speed "$read_result")
    if echo "$read_speed" | grep -qE '^[0-9]'; then
        read_speed="${read_speed} MB/s"
    fi
    echo -e "  Read Speed: ${BLUE}${read_speed}${NC}"
    echo "  Sequential Read: ${read_speed}" >> "$RESULTS_FILE"

    # Random I/O Test (if fio is available)
    if command -v fio &> /dev/null; then
        local ioengine
        ioengine=$(get_fio_ioengine)

        echo -e "  ${GREEN}Random 4K Write (fio)...${NC}"
        fio_result=$(fio --name=randwrite --filename="${testfile}" --ioengine="${ioengine}" --rw=randwrite --bs=4k --size=64M --numjobs=1 --runtime=10 --time_based --output-format=terse 2>/dev/null | cut -d';' -f48)
        if [ -n "$fio_result" ]; then
            fio_speed=$(echo "scale=2; ${fio_result}/1024" | bc 2>/dev/null || echo "${fio_result}")
            echo -e "  Random 4K Write: ${BLUE}${fio_speed} MB/s${NC}"
            echo "  Random 4K Write: ${fio_speed} MB/s" >> "$RESULTS_FILE"
        fi

        echo -e "  ${GREEN}Random 4K Read (fio)...${NC}"
        fio_result=$(fio --name=randread --filename="${testfile}" --ioengine="${ioengine}" --rw=randread --bs=4k --size=64M --numjobs=1 --runtime=10 --time_based --output-format=terse 2>/dev/null | cut -d';' -f7)
        if [ -n "$fio_result" ]; then
            fio_speed=$(echo "scale=2; ${fio_result}/1024" | bc 2>/dev/null || echo "${fio_result}")
            echo -e "  Random 4K Read: ${BLUE}${fio_speed} MB/s${NC}"
            echo "  Random 4K Read: ${fio_speed} MB/s" >> "$RESULTS_FILE"
        fi
    else
        echo -e "  ${YELLOW}fio not installed - skipping random I/O tests${NC}"
        echo -e "  ${YELLOW}Install with: brew install fio${NC}"
        echo "  (fio not installed - random I/O tests skipped)" >> "$RESULTS_FILE"
    fi

    # Cleanup
    rm -f "${testfile}"

    echo "" >> "$RESULTS_FILE"
    echo ""
}

# Detect which host we're on and run appropriate benchmarks
case "$HOSTNAME" in
    "torrentbox"|"torrentbox.local")
        echo -e "${BLUE}Detected: Torrentbox (192.168.10.141)${NC}"
        echo ""

        # Local USB drive
        benchmark_drive "/mnt/media" "Local USB Drive (1TB exFAT)"

        # NAS mounts
        benchmark_drive "/mnt/nas/movies" "NAS Movies (SMB)"
        benchmark_drive "/mnt/nas/tv" "NAS TV (SMB)"
        benchmark_drive "/mnt/nas/torrents" "NAS Torrents (SMB)"
        ;;

    "nas01"|"nas01.local"|"nas")
        echo -e "${BLUE}Detected: NAS Server (192.168.10.105)${NC}"
        echo ""

        # Main media disk
        benchmark_drive "/mnt/media-disk" "Media Disk (4.6TB)"

        # Archive disk (find the actual path)
        if [ -d "/srv" ]; then
            archive_path=$(find /srv -maxdepth 1 -type d -name "dev-disk-*" 2>/dev/null | head -1)
            if [ -n "$archive_path" ]; then
                benchmark_drive "$archive_path" "Archive Disk (916GB)"
            fi
        fi
        ;;

    "herring"|"herring.local"|"plex")
        echo -e "${BLUE}Detected: Plex/Emby Server (192.168.10.150)${NC}"
        echo ""

        # Local USB drives
        benchmark_drive "/mnt/usb2" "Local USB Drive 1 (932GB ext4)"
        benchmark_drive "/mnt/media" "Local USB Drive 2 (916GB ext4)"

        # NAS mounts
        benchmark_drive "/mnt/nas/Movies" "NAS Movies (SMB)"
        benchmark_drive "/mnt/nas/TV" "NAS TV (SMB)"

        # Torrentbox mount
        benchmark_drive "/mnt/torrentbox" "Torrentbox Share (SMB)"
        ;;

    "Johns-MacBook-Pro"*|"jd-macbook"*|"macbook"*)
        echo -e "${BLUE}Detected: Mac Workstation (192.168.10.145)${NC}"
        echo ""

        # Local SSD (home directory)
        benchmark_drive "$HOME" "Internal SSD (Apple M4 Pro)"

        # NAS SMB mounts (macOS mounts under /Volumes/)
        [ -d "/Volumes/Movies" ] && benchmark_drive "/Volumes/Movies" "NAS Movies (SMB)"
        [ -d "/Volumes/TV" ] && benchmark_drive "/Volumes/TV" "NAS TV (SMB)"
        [ -d "/Volumes/Torrents" ] && benchmark_drive "/Volumes/Torrents" "NAS Torrents (SMB)"
        [ -d "/Volumes/Music" ] && benchmark_drive "/Volumes/Music" "NAS Music (SMB)"
        [ -d "/Volumes/Books" ] && benchmark_drive "/Volumes/Books" "NAS Books (SMB)"

        # Torrentbox share
        [ -d "/Volumes/Media" ] && benchmark_drive "/Volumes/Media" "Torrentbox Media (SMB)"

        # Check if no NAS mounts were found
        if [ ! -d "/Volumes/Movies" ] && [ ! -d "/Volumes/TV" ]; then
            echo -e "${YELLOW}No NAS shares mounted. Connect via Finder:${NC}"
            echo -e "${YELLOW}  smb://192.168.10.105/Movies${NC}"
            echo -e "${YELLOW}  smb://192.168.10.105/TV${NC}"
            echo ""
        fi
        ;;

    *)
        echo -e "${YELLOW}Unknown host: ${HOSTNAME}${NC}"
        echo -e "${YELLOW}Running generic benchmark on common paths...${NC}"
        echo ""

        # Try common paths (Linux)
        [ -d "/mnt/media" ] && benchmark_drive "/mnt/media" "Media Mount"
        [ -d "/mnt/nas" ] && benchmark_drive "/mnt/nas" "NAS Mount"
        [ -d "/mnt/usb2" ] && benchmark_drive "/mnt/usb2" "USB2 Mount"

        # Try common paths (macOS)
        [ -d "/Volumes/Movies" ] && benchmark_drive "/Volumes/Movies" "Movies (SMB)"
        [ -d "/Volumes/TV" ] && benchmark_drive "/Volumes/TV" "TV (SMB)"
        ;;
esac

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Benchmark Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Results saved to: ${GREEN}${RESULTS_FILE}${NC}"
echo ""
echo -e "${YELLOW}To view results:${NC}"
echo "  cat ${RESULTS_FILE}"
echo ""
