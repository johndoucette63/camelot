#!/usr/bin/env bash
# Vaultwarden snapshot — online SQLite backup + attachments + sends.
#
# Runs as a cron job on HOLYGRAIL. Uses sqlite3 .backup so it's safe while
# the container is live (no need to stop Vaultwarden).
#
# Retention matches the tank/ZFS policy: 7 daily, 4 weekly, 6 monthly.
# Backups land on the NVMe; once tank is online (specs/020-storage-evolution),
# add a second cron line to rsync /var/backups/vaultwarden/ -> /tank/archive/.
#
# Install:
#   sudo install -m 0755 backup.sh /usr/local/sbin/vaultwarden-backup
#   sudo install -d -o root -g root -m 0750 /var/backups/vaultwarden
#   sudo tee /etc/cron.d/vaultwarden-backup > /dev/null <<'EOF'
#   30 3 * * *  root  /usr/local/sbin/vaultwarden-backup >> /var/log/vaultwarden-backup.log 2>&1
#   EOF
set -euo pipefail

CONTAINER="${CONTAINER:-vaultwarden}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/vaultwarden}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"
KEEP_MONTHLY="${KEEP_MONTHLY:-6}"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$BACKUP_DIR"/{daily,weekly,monthly}

# Online SQLite snapshot via vaultwarden's built-in backup command
# (the image doesn't ship a sqlite3 CLI). It writes a timestamped file
# into /data; copy it out and remove the in-container copy.
backup_line=$(docker exec "$CONTAINER" /vaultwarden backup 2>&1)
backup_file=$(printf "%s" "$backup_line" | sed -nE "s|.*'(data/[^']+)'.*|\1|p")
if [ -z "$backup_file" ]; then
    echo "ERROR: could not parse backup filename from: $backup_line" >&2
    exit 1
fi
docker cp "$CONTAINER:/$backup_file" "$work/db.sqlite3"
docker exec "$CONTAINER" rm -f "/$backup_file"

# Cold-copy the rest (small files: keys, attachments, sends, config).
for path in rsa_key.pem rsa_key.pub.pem config.json attachments sends; do
    if docker exec "$CONTAINER" test -e "/data/$path"; then
        docker cp "$CONTAINER:/data/$path" "$work/" 2>/dev/null || true
    fi
done

archive="$BACKUP_DIR/daily/vaultwarden-$ts.tar.gz"
tar -czf "$archive" -C "$work" .
chmod 0600 "$archive"

dow="$(date -u +%u)"  # 1=Mon..7=Sun — promote Sunday's backup to weekly
dom="$(date -u +%d)"  # 01..31      — promote 1st-of-month to monthly
[[ "$dow" == "7" ]] && cp -p "$archive" "$BACKUP_DIR/weekly/"
[[ "$dom" == "01" ]] && cp -p "$archive" "$BACKUP_DIR/monthly/"

# Prune: keep newest N in each tier.
prune() {
    local dir="$1" keep="$2"
    find "$dir" -maxdepth 1 -type f -name 'vaultwarden-*.tar.gz' -printf '%T@ %p\n' \
        | sort -rn | awk -v k="$keep" 'NR>k {print $2}' | xargs -r rm -f
}
prune "$BACKUP_DIR/daily"   "$KEEP_DAILY"
prune "$BACKUP_DIR/weekly"  "$KEEP_WEEKLY"
prune "$BACKUP_DIR/monthly" "$KEEP_MONTHLY"

echo "[$(date -u +%FT%TZ)] vaultwarden backup ok: $archive ($(du -h "$archive" | cut -f1))"
