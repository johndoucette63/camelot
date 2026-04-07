#!/usr/bin/env bash
# Configure NAS SMB mounts on HOLYGRAIL
# Mounts Movies, TV, and Music shares from the NAS Pi (192.168.10.105)
# Usage: sudo ./setup-nas-mounts.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

NAS_IP="192.168.10.105"
CREDS_FILE="/etc/samba/nas-creds"
MOUNT_OPTS="credentials=${CREDS_FILE},uid=1000,gid=1000,file_mode=0664,dir_mode=0775,nofail,_netdev,x-systemd.automount,x-systemd.requires=network-online.target"

# Shares to mount: NAS_SHARE -> LOCAL_MOUNT
declare -A SHARES=(
    ["Movies"]="/mnt/nas/movies"
    ["TV"]="/mnt/nas/tv"
    ["Music"]="/mnt/nas/music"
)

echo "=== NAS SMB Mount Setup ==="
echo ""

# --- Install cifs-utils ---
echo "Installing cifs-utils..."
apt-get install -y cifs-utils > /dev/null 2>&1
echo "  Done."

# --- Create mount points ---
echo "Creating mount points..."
for share in "${!SHARES[@]}"; do
    mkdir -p "${SHARES[$share]}"
    echo "  ${SHARES[$share]}"
done

# --- Create credentials file ---
if [[ -f "$CREDS_FILE" ]]; then
    echo "Credentials file already exists: $CREDS_FILE"
else
    echo "Creating credentials file: $CREDS_FILE"
    mkdir -p "$(dirname "$CREDS_FILE")"
    cat > "$CREDS_FILE" <<'EOF'
username=REPLACE_WITH_NAS_USER
password=REPLACE_WITH_NAS_PASSWORD
EOF
    chmod 600 "$CREDS_FILE"
    echo "  IMPORTANT: Edit $CREDS_FILE with your NAS credentials before mounting!"
    echo "  Run: sudo nano $CREDS_FILE"
fi

# --- Add fstab entries ---
echo "Configuring /etc/fstab..."
FSTAB_CHANGED=false

for share in "${!SHARES[@]}"; do
    FSTAB_LINE="//${NAS_IP}/${share} ${SHARES[$share]} cifs ${MOUNT_OPTS} 0 0"

    if grep -qF "//${NAS_IP}/${share}" /etc/fstab; then
        echo "  Already in fstab: //${NAS_IP}/${share}"
    else
        echo "$FSTAB_LINE" >> /etc/fstab
        echo "  Added: //${NAS_IP}/${share} -> ${SHARES[$share]}"
        FSTAB_CHANGED=true
    fi
done

# --- Verify credentials before mounting ---
if grep -q "REPLACE_WITH" "$CREDS_FILE"; then
    echo ""
    echo "WARNING: NAS credentials not yet configured!"
    echo "  1. Edit $CREDS_FILE with your NAS username and password"
    echo "  2. Then run: sudo mount -a"
    echo "  3. Verify with: ls /mnt/nas/movies"
    exit 0
fi

# --- Mount if credentials are set ---
if [[ "$FSTAB_CHANGED" == "true" ]]; then
    echo "Mounting shares..."
    systemctl daemon-reload
    mount -a
fi

# --- Verify ---
echo ""
echo "Verifying mounts..."
MOUNT_OK=true
for share in "${!SHARES[@]}"; do
    if mountpoint -q "${SHARES[$share]}" 2>/dev/null; then
        echo "  [OK] ${SHARES[$share]}"
    else
        echo "  [NOT MOUNTED] ${SHARES[$share]}"
        MOUNT_OK=false
    fi
done

if [[ "$MOUNT_OK" == "true" ]]; then
    echo ""
    echo "All NAS shares mounted successfully."
else
    echo ""
    echo "Some shares are not mounted. Check credentials and NAS connectivity."
    echo "Try: sudo mount -a"
fi
