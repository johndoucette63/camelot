# Quickstart: Plex Media Server Migration

**Feature**: 004-plex-migration  
**Date**: 2026-04-07

## Prerequisites

- HOLYGRAIL running Ubuntu 24.04 with Docker and NVIDIA container toolkit (Phase 1 complete)
- SSH access to HOLYGRAIL: `ssh john@holygrail`
- SSH access to Media Server Pi: `ssh pi@192.168.10.150`
- SSH access to Torrentbox: `ssh john@192.168.10.141` (for Sonarr/Radarr updates)
- NAS Pi (192.168.10.105) running and serving SMB shares
- Plex Pass subscription (required for hardware transcoding)
- Plex account credentials for claim token

## Migration Sequence

### Step 1: Mount NAS Shares on HOLYGRAIL

```bash
ssh john@holygrail

# Install CIFS utilities
sudo apt install cifs-utils

# Create mount points
sudo mkdir -p /mnt/nas/{movies,tv,music}

# Create NAS credentials file (mode 600)
sudo tee /etc/samba/nas-creds <<EOF
username=<NAS_USER>
password=<NAS_PASSWORD>
EOF
sudo chmod 600 /etc/samba/nas-creds

# Add to /etc/fstab (see setup-nas-mounts.sh for automated version)
# Test with: sudo mount -a
```

### Step 2: Deploy Plex on HOLYGRAIL

```bash
# From Mac workstation — push compose files to HOLYGRAIL
# Or SSH into HOLYGRAIL and create the compose file

# Generate claim token at https://www.plex.tv/claim (expires in 4 minutes!)
# Set PLEX_CLAIM in .env file
# Start container:
cd ~/docker/plex  # or wherever compose file lives
docker compose up -d

# Verify GPU access:
docker exec plex nvidia-smi
```

### Step 3: Configure Plex

1. Open http://holygrail:32400/web
2. Complete setup wizard (server name, library setup)
3. Settings > Transcoder: enable "Use hardware acceleration when available"
4. Settings > Network > LAN Networks: add `192.168.10.0/24`
5. Settings > Remote Access: enable and verify
6. Add libraries pointing at /movies, /tv, /music (container paths mapped to NAS mounts)

### Step 4: Validate

```bash
# Run verification script
bash infrastructure/holygrail/verify-plex.sh

# Manual checks:
# - Play a file that requires transcoding, confirm "(hw)" in dashboard
# - Check from external network (phone on cellular)
# - Verify NAS mounts survive reboot: sudo reboot
```

### Step 5: Re-invite Shared Users

1. Settings > Users & Sharing > invite existing external users to the new server
2. Confirm shared users can see and stream from the new server

### Step 6: Update Torrent Pipeline

1. Open Sonarr (192.168.10.141:8989) > Settings > Connect > Plex
2. Change host from `192.168.10.150` to `192.168.10.129`
3. Repeat for Radarr (192.168.10.141:7878)
4. Test: trigger a manual library scan from Sonarr/Radarr

### Step 7: Cutover — Stop Pi Media Services

```bash
# Only after validating HOLYGRAIL Plex is fully functional!
ssh pi@192.168.10.150

# Stop Plex
sudo systemctl stop plexmediaserver
sudo systemctl disable plexmediaserver

# Stop Emby
docker stop emby
docker rm emby
# Remove from any docker-compose if applicable

# Verify Pi-hole still running
pihole status
```

### Step 8: Update Documentation

- Update `docs/INFRASTRUCTURE.md` with new Plex location and Emby retirement
- Update `scripts/pi-status.sh` if Media Server Pi role changes
- Open UFW port on HOLYGRAIL: `sudo ufw allow 32400/tcp comment "Plex Media Server"`

## Key Ports

| Port | Service | Firewall |
|------|---------|----------|
| 32400/tcp | Plex web/API | UFW + router forward for remote access |

## Rollback

If HOLYGRAIL Plex doesn't work out during parallel run:
1. Plex on Pi is still running — no action needed, users continue streaming from "Herring"
2. Stop HOLYGRAIL Plex: `docker compose down`
3. Revert Sonarr/Radarr Plex host to `192.168.10.150`
