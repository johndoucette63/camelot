# Data Model: Plex Media Server Migration

**Feature**: 004-plex-migration  
**Date**: 2026-04-07

## Overview

This is an infrastructure migration feature, not a database application. The "data model" describes the infrastructure components, their relationships, and state transitions during migration.

## Infrastructure Components

### Plex Media Server (HOLYGRAIL)

| Attribute | Value |
|-----------|-------|
| Host | holygrail (192.168.10.129) |
| Container image | lscr.io/linuxserver/plex:latest |
| Network mode | host |
| GPU | RTX 2070 Super via nvidia runtime |
| Config storage | Local Docker volume (never SMB) |
| Transcode cache | Local path on NVMe |
| Media source | NAS SMB mounts at /mnt/nas/* |
| Web UI | http://holygrail:32400/web |
| Restart policy | unless-stopped |

### NAS SMB Mounts (on HOLYGRAIL)

| Share | Source | Mount Point |
|-------|--------|-------------|
| Movies | //192.168.10.105/Movies | /mnt/nas/movies |
| TV | //192.168.10.105/TV | /mnt/nas/tv |
| Music | //192.168.10.105/Music | /mnt/nas/music |

Mount type: CIFS via fstab with systemd automount options.

### Media Server Pi (192.168.10.150) — State Transitions

```
Current State          → Parallel Run           → Final State
─────────────────────────────────────────────────────────────
Plex: running (systemd)  Plex: running (standby)   Plex: stopped
Emby: running (Docker)   Emby: running (standby)   Emby: stopped (retired)
Pi-hole: running          Pi-hole: running           Pi-hole: running
Role: Media Server        Role: Media Server         Role: Pi-hole DNS only
```

### Torrentbox Integration (192.168.10.141)

| App | Current Plex Target | New Plex Target |
|-----|-------------------|-----------------|
| Sonarr | 192.168.10.150:32400 | 192.168.10.129:32400 |
| Radarr | 192.168.10.150:32400 | 192.168.10.129:32400 |

## File Ownership

All NAS-mounted media and Plex config must use consistent UID/GID:
- PUID: 1000 (john on HOLYGRAIL)
- PGID: 1000 (john on HOLYGRAIL)

This matches the existing convention on Torrentbox (PUID=1000, PGID=1000).

## Configuration Files (Not Committed)

| File | Location on HOLYGRAIL | Purpose |
|------|----------------------|---------|
| NAS credentials | /etc/samba/nas-creds (mode 600) | SMB mount authentication |
| Plex .env | alongside docker-compose.yml (gitignored) | PLEX_CLAIM token, TZ |
| Plex config | Docker volume: plex_config | Plex database, preferences, metadata cache |
| Transcode cache | /tmp/plex-transcode (or local path) | Temporary transcode output |
