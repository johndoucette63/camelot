# Research: Plex Media Server Migration

**Feature**: 004-plex-migration  
**Date**: 2026-04-07

## R-001: Plex Docker Image Selection

**Decision**: Use `linuxserver/plex` (`lscr.io/linuxserver/plex:latest`)

**Rationale**: The linuxserver image bundles the necessary NVIDIA libraries inside the container for NVENC transcoding. The official `plexinc/pms-docker` image is missing some NVIDIA packages that can prevent hardware transcoding from working. The linuxserver image is also actively maintained (last updated April 6, 2026), uses PUID/PGID environment variables (consistent with existing Torrentbox containers), and is based on Ubuntu Noble.

**Alternatives considered**:
- `plexinc/pms-docker`: Official image but lacks built-in NVIDIA packages. Would require manual NVIDIA library installation inside the container. Less frequent updates.

## R-002: GPU Passthrough Method

**Decision**: Use `runtime: nvidia` with `NVIDIA_VISIBLE_DEVICES=all` in Docker Compose

**Rationale**: This is consistent with how the HOLYGRAIL Docker/GPU infrastructure was validated in F1.2 (`verify-docker-gpu.sh` uses `--runtime=nvidia --gpus all`). The modern `deploy.resources.reservations.devices` approach also works but `runtime: nvidia` matches the existing verified setup. HOLYGRAIL has a single RTX 2070 Super.

**Alternatives considered**:
- `deploy.resources.reservations.devices`: Modern Compose syntax. Works but untested on this specific HOLYGRAIL setup. Could use in future.
- `--gpus all` CLI flag: CLI-only, not available in Compose file format.

**Note**: Consumer NVIDIA GPUs (RTX 2070 Super) are limited to 3 simultaneous NVENC encoding sessions by default. The `keylase/nvidia-patch` can remove this limit on the host driver if needed. For household usage (3-5 streams), the default limit is likely sufficient.

## R-003: SMB Mount Strategy

**Decision**: fstab with systemd automount options (`x-systemd.automount`, `_netdev`, `nofail`)

**Rationale**: Simplest and most reliable for Docker container access on Ubuntu 24.04. This matches the existing pattern used on Torrentbox (fstab CIFS mounts). The systemd options handle boot ordering (waits for network), auto-retry on NAS disconnect, and non-blocking boot if NAS is unavailable.

**Alternatives considered**:
- Plain fstab (no systemd options): Fails if NAS boots after HOLYGRAIL; no retry mechanism.
- systemd .mount/.automount units: More verbose config files; systemd auto-generates these from fstab anyway.
- autofs: More complex setup, designed for many dynamic mounts. Overkill for 3-5 static NAS shares.

**Critical warning**: Plex `/config` directory (SQLite database) must NEVER be on an SMB mount. SMB does not support the file locking SQLite requires and will corrupt the database. Config stays on local disk.

**Mount options**: `credentials=/etc/samba/nas-creds,uid=1000,gid=1000,file_mode=0664,dir_mode=0775,nofail,_netdev,x-systemd.automount,x-systemd.requires=network-online.target`

## R-004: Plex Server Claim Process

**Decision**: Use `PLEX_CLAIM` environment variable on first container start

**Rationale**: Simplest approach for headless server. Generate a claim token at https://www.plex.tv/claim, set it in the `.env` file, and start the container within 4 minutes (token expiry). After the first successful claim, the token is no longer needed and can be removed from `.env`.

**Alternatives considered**:
- SSH tunnel method: Skip claim token, SSH tunnel port 32400 from Mac to HOLYGRAIL, then access localhost:32400/web to complete setup wizard. Works but more manual steps.

## R-005: Network Mode and Remote Access

**Decision**: Use `network_mode: host` with UFW rule for port 32400/tcp

**Rationale**: Host networking is recommended for Plex — it avoids Docker bridge NAT complications and enables full local discovery (GDM, DLNA, Bonjour). All Plex ports are automatically available on the host IP without explicit port mapping. For remote access, only port 32400/tcp needs to be opened on UFW and forwarded on the router.

**Configuration needed**:
1. UFW: `sudo ufw allow 32400/tcp comment "Plex Media Server"`
2. Router: Forward external port 32400 (TCP) to 192.168.10.129:32400
3. Plex Settings > Network > LAN Networks: set `192.168.10.0/24`

**Plex ports** (all automatic with host networking):
- 32400/tcp — Primary Plex communication (required)
- 1900/udp — DLNA discovery
- 5353/udp — Bonjour/Avahi discovery
- 8324/tcp — Roku companion
- 32410, 32412-32414/udp — GDM network discovery
- 32469/tcp — DLNA media access

## R-006: NAS Shares to Mount

**Decision**: Mount Movies, TV, and Music from NAS (192.168.10.105). Match Torrentbox naming convention.

**Rationale**: These are the three media types Plex serves. The Torrentbox already mounts these shares at `/mnt/nas/movies`, `/mnt/nas/tv`, `/mnt/nas/music`. Using the same mount paths on HOLYGRAIL keeps the system consistent.

**Mount points on HOLYGRAIL**:
- `//192.168.10.105/Movies` → `/mnt/nas/movies`
- `//192.168.10.105/TV` → `/mnt/nas/tv`
- `//192.168.10.105/Music` → `/mnt/nas/music`

## R-007: Sonarr/Radarr Reconfiguration

**Decision**: Update Plex connection settings in Sonarr and Radarr on Torrentbox to point at HOLYGRAIL (192.168.10.129:32400)

**Rationale**: Currently Sonarr/Radarr notify the Pi-based Plex (192.168.10.150:32400) to scan for new media. After migration, they must point to HOLYGRAIL. This is a settings change in each app's UI under Settings > Connect > Plex.

**Steps**: Navigate to each app's web UI, update the Plex server host from `192.168.10.150` to `192.168.10.129`.
