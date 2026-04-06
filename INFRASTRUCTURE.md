# Home Media Infrastructure

## Network Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          192.168.10.0/24 Network                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │   TORRENTBOX    │  │      NAS        │  │   MEDIA SERVER  │             │
│  │ 192.168.10.141  │  │ 192.168.10.105  │  │ 192.168.10.150  │             │
│  │                 │  │                 │  │                 │             │
│  │ Pi 5 (8GB)      │  │ Pi 4 (4GB)      │  │ Pi 5 (8GB)      │             │
│  │ Debian Trixie   │  │ OpenMediaVault  │  │ Debian Bookworm │             │
│  │                 │  │                 │  │                 │             │
│  │ Services:       │  │ Services:       │  │ Services:       │             │
│  │ - Deluge        │  │ - Samba/SMB     │  │ - Plex          │             │
│  │ - Sonarr        │  │ - Pi-hole DNS   │  │ - Emby          │             │
│  │ - Radarr        │  │                 │  │                 │             │
│  │ - Prowlarr      │  │                 │  │                 │             │
│  │ - Lidarr        │  │                 │  │                 │             │
│  │ - LazyLibrarian │  │                 │  │                 │             │
│  │ - OpenVPN (PIA) │  │                 │  │                 │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           │    SMB/CIFS        │      SMB/CIFS      │                       │
│           └────────────────────┼────────────────────┘                       │
│                                │                                            │
│                      ┌─────────┴─────────┐                                  │
│                      │   NAS STORAGE     │                                  │
│                      │   4.6TB Media     │                                  │
│                      └───────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Torrentbox (192.168.10.141)

### System Info

| Property | Value |
|----------|-------|
| Hostname | torrentbox |
| Hardware | Raspberry Pi 5 (8GB RAM) + Pironman5 case |
| OS | Raspberry Pi OS Lite 64-bit (Debian Trixie) |
| SSH | `ssh john@192.168.10.141` |

### Storage

| Disk | Size | Format | Mount Point | Description |
|------|------|--------|-------------|-------------|
| SD Card | 917GB | ext4 | / | OS drive |
| Samsung T7 USB | 932GB | exFAT | /mnt/media | Travel media (portable) |

**Travel Media Structure:**
```
/mnt/media/
├── Movies/
└── TV/
```

### Docker Services

| Service | Port | Description |
|---------|------|-------------|
| Deluge Web UI | 8112 | Torrent client |
| Deluge Daemon | 58846 | RPC interface |
| Sonarr | 8989 | TV show management |
| Radarr | 7878 | Movie management |
| Prowlarr | 9696 | Indexer management |
| FlareSolverr | 8191 | CloudFlare bypass |
| Lidarr | 8686 | Music management |
| LazyLibrarian | 5299 | Book management |

### Docker Compose

Location: `/home/john/docker/docker-compose.yml`

```yaml
services:
  deluge:
    image: lscr.io/linuxserver/deluge:latest
    container_name: deluge
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Denver
      - DELUGE_LOGLEVEL=error
    volumes:
      - /home/john/docker/deluge:/config
      - /mnt/nas/torrents:/downloads
    ports:
      - 8112:8112
      - 58846:58846
      - 6881:6881
      - 6881:6881/udp
    restart: unless-stopped

  sonarr:
    image: lscr.io/linuxserver/sonarr:latest
    container_name: sonarr
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Denver
    volumes:
      - /home/john/docker/sonarr:/config
      - /mnt/nas/tv:/tv
      - /mnt/nas/torrents:/downloads
      - /mnt/media/TV:/travel-tv
    ports:
      - 8989:8989
    restart: unless-stopped

  radarr:
    image: lscr.io/linuxserver/radarr:latest
    container_name: radarr
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Denver
    volumes:
      - /home/john/docker/radarr:/config
      - /mnt/nas/movies:/movies
      - /mnt/nas/torrents:/downloads
      - /mnt/media/Movies:/travel-movies
    ports:
      - 7878:7878
    restart: unless-stopped

  prowlarr:
    image: lscr.io/linuxserver/prowlarr:latest
    container_name: prowlarr
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Denver
    volumes:
      - /home/john/docker/prowlarr:/config
    ports:
      - 9696:9696
    restart: unless-stopped

  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: flaresolverr
    environment:
      - LOG_LEVEL=info
      - TZ=America/Denver
    ports:
      - 8191:8191
    restart: unless-stopped

  lidarr:
    image: lscr.io/linuxserver/lidarr:latest
    container_name: lidarr
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Denver
    volumes:
      - /home/john/docker/lidarr:/config
      - /mnt/nas/music:/music
      - /mnt/nas/torrents:/downloads
    ports:
      - 8686:8686
    restart: unless-stopped

  lazylibrarian:
    image: lscr.io/linuxserver/lazylibrarian:latest
    container_name: lazylibrarian
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Denver
      - DOCKER_MODS=linuxserver/mods:universal-calibre
    volumes:
      - /home/john/docker/lazylibrarian:/config
      - /mnt/nas/books:/books
      - /mnt/nas/torrents:/downloads
    ports:
      - 5299:5299
    restart: unless-stopped
```

### NAS Mounts

`/etc/fstab` entries:
```
//192.168.10.105/Movies    /mnt/nas/movies    cifs    credentials=/etc/nas-credentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev    0    0
//192.168.10.105/TV        /mnt/nas/tv        cifs    credentials=/etc/nas-credentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev    0    0
//192.168.10.105/Torrents  /mnt/nas/torrents  cifs    credentials=/etc/nas-credentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev    0    0
//192.168.10.105/Music     /mnt/nas/music     cifs    credentials=/etc/nas-credentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev    0    0
//192.168.10.105/Books     /mnt/nas/books     cifs    credentials=/etc/nas-credentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev    0    0
UUID=EFEE-EB42 /mnt/media exfat defaults,uid=1000,gid=1000,nofail 0 0
```

NAS credentials: `/etc/nas-credentials` (chmod 600)

### Samba Share

`/etc/samba/smb.conf`:
```ini
[Media]
   comment = Travel Media (Samsung T7)
   path = /mnt/media
   browseable = yes
   read only = no
   guest ok = no
   valid users = john
   create mask = 0755
   directory mask = 0755
```

Network access: `\\192.168.10.141\Media`

### VPN Configuration

PIA VPN with kill-switch enabled.

| Setting | Value |
|---------|-------|
| Config | /etc/openvpn/pia.conf |
| Server | us-denver.privacy.network:1197 |
| Protocol | UDP |
| Cipher | AES-256-CBC |

**Kill-switch script** (`/etc/openvpn/vpn-up.sh`):
- Allows loopback and local network (192.168.10.0/24)
- Allows Docker network (172.16.0.0/12)
- Allows VPN tunnel traffic
- Blocks all other outbound traffic

**Service management:**
```bash
sudo systemctl status openvpn@pia
sudo systemctl restart openvpn@pia
```

### Deluge Settings

| Setting | Value |
|---------|-------|
| Download location | /downloads/incomplete |
| Move completed | /downloads/complete |
| Stop seed ratio | 0.0 (immediate) |
| Remove at ratio | Yes |
| Web password | subterra |
| Daemon password | subterra |

---

## NAS Server (192.168.10.105)

### System Info

| Property | Value |
|----------|-------|
| Hostname | nas01 |
| Hardware | Raspberry Pi 4 (4GB RAM) |
| OS | OpenMediaVault (Debian-based) |
| SSH | `ssh pi@192.168.10.105` |

### Storage

| Disk | Size | Used | Mount Point |
|------|------|------|-------------|
| Media Disk | 4.6TB | 2.8TB (61%) | /mnt/media-disk |
| Archive Disk | 916GB | 44GB (5%) | /srv/dev-disk-... |
| SD Card | 117GB | 3.7GB (4%) | / |

### SMB Shares

| Share | Path | Size |
|-------|------|------|
| Movies | /mnt/media-disk/MediaStorage/Media/Movies/ | 1.2TB |
| TV | /mnt/media-disk/MediaStorage/Media/TV/ | 980GB |
| Torrents | /mnt/media-disk/MediaStorage/Media/torrent-downloads/ | - |
| Music | /mnt/media-disk/MediaStorage/Media/Music/ | 5.3GB |
| Books | /mnt/media-disk/MediaStorage/Media/Books/ | 2.9GB |

### Services

| Service | Port |
|---------|------|
| OpenMediaVault | 80 |
| Pi-hole | 80/admin, 53 |
| Samba | 139, 445 |

---

## Media Server (192.168.10.150)

### System Info

| Property | Value |
|----------|-------|
| Hostname | herring |
| Hardware | Raspberry Pi 5 (8GB RAM) |
| OS | Debian GNU/Linux 12 (Bookworm) |
| SSH | `ssh pi@192.168.10.150` |

### Storage

| Disk | Size | Format | Mount Point | Description |
|------|------|--------|-------------|-------------|
| NVMe SSD | 465GB | ext4 | / | OS drive |
| USB Drive 1 | 932GB | ntfs | /mnt/usb2 | Local media |
| USB Drive 2 | 932GB | ext4 | /mnt/media | Local media |

### Services

| Service | Port | Type |
|---------|------|------|
| Plex | 32400 | systemd |
| Emby | 8096 (HTTP), 8920 (HTTPS) | Docker |

### NAS & Torrentbox Mounts

```
/mnt/nas/Movies      → //192.168.10.105/Movies
/mnt/nas/TV          → //192.168.10.105/TV
/mnt/torrentbox      → //192.168.10.141/Media
```

### Emby Docker

```bash
docker run -d \
  --name emby \
  --restart unless-stopped \
  -e PUID=1000 -e PGID=1000 -e TZ=America/Denver \
  -p 8096:8096 -p 8920:8920 \
  -v /home/pi/docker/emby:/config \
  -v /mnt/nas/Movies:/data/nas-movies \
  -v /mnt/nas/TV:/data/nas-tv \
  -v /mnt/usb2/Movies:/data/local-movies \
  -v /mnt/usb2/TV:/data/local-tv \
  -v /mnt/media/Movies:/data/media-movies \
  -v /mnt/media/TV:/data/media-tv \
  -v /mnt/torrentbox/Movies:/data/torrentbox-movies \
  -v /mnt/torrentbox/TV:/data/torrentbox-tv \
  lscr.io/linuxserver/emby:latest
```

---

## Application Configuration

### Root Folders

| Application | Container Path | Host Path |
|-------------|----------------|-----------|
| Sonarr | /tv | /mnt/nas/tv |
| Sonarr | /travel-tv | /mnt/media/TV |
| Radarr | /movies | /mnt/nas/movies |
| Radarr | /travel-movies | /mnt/media/Movies |
| Lidarr | /music | /mnt/nas/music |
| LazyLibrarian | /books | /mnt/nas/books |

### Download Client (Deluge)

For all *arr apps:

| Setting | Value |
|---------|-------|
| Host | deluge |
| Port | 8112 |
| Password | subterra |

Categories: `tv-sonarr`, `radarr`, `lidarr`

### Prowlarr Apps

| App | Server | API Key |
|-----|--------|---------|
| Sonarr | http://sonarr:8989 | ebb7706d9d7f4401939338bab7ebc103 |
| Radarr | http://radarr:7878 | e6e70d60d9aa4daca794a64ea858c63a |

FlareSolverr: `http://flaresolverr:8191`

### API Keys

| Service | API Key |
|---------|---------|
| Sonarr | ebb7706d9d7f4401939338bab7ebc103 |
| Radarr | e6e70d60d9aa4daca794a64ea858c63a |
| Prowlarr | 272a8c0521614ce8bfdf9bf413a746f5 |
| Lidarr | 2d4510f26b1b460fad199ab39a31c33d |

### LazyLibrarian Kindle

| Setting | Value |
|---------|-------|
| Email From | doucette.j@gmail.com |
| Kindle Address | doucette.j_Kindle@kindle.com |
| SMTP | smtp.gmail.com:587 (TLS) |

---

## Data Flow

```
1. Add media to Sonarr/Radarr
         │
         ▼
2. Prowlarr searches indexers
   (FlareSolverr bypasses CloudFlare)
         │
         ▼
3. Torrent sent to Deluge (via VPN)
         │
         ▼
4. Downloaded to /downloads/incomplete
         │
         ▼
5. Moved to /downloads/complete
   (seeding stops, torrent removed)
         │
         ▼
6. Sonarr/Radarr imports and renames
   TV → /tv → /mnt/nas/tv
   Movies → /movies → /mnt/nas/movies
         │
         ▼
7. Plex/Emby auto-detect new media
```

---

## Web Interfaces

| Service | URL |
|---------|-----|
| Deluge | http://192.168.10.141:8112 |
| Sonarr | http://192.168.10.141:8989 |
| Radarr | http://192.168.10.141:7878 |
| Prowlarr | http://192.168.10.141:9696 |
| Lidarr | http://192.168.10.141:8686 |
| LazyLibrarian | http://192.168.10.141:5299 |
| Plex | http://192.168.10.150:32400/web |
| Emby | http://192.168.10.150:8096 |
| OpenMediaVault | http://192.168.10.105 |
| Pi-hole | http://192.168.10.105/admin |

---

## Storage Summary

| Location | Capacity | Used | Available |
|----------|----------|------|-----------|
| NAS Media Disk | 4.6TB | 2.8TB | 1.8TB |
| NAS Archive Disk | 916GB | 44GB | 872GB |
| Media Server NVMe | 465GB | - | ~465GB |
| Media Server USB 1 | 932GB | - | ~932GB |
| Media Server USB 2 | 932GB | - | ~932GB |
| Torrentbox SD | 931GB | 4.3GB | 876GB |
| Torrentbox USB (Travel) | 932GB | - | ~932GB |
| **Total** | **~9.7TB** | **~2.9TB** | **~6.8TB** |

---

## Credentials

| Service | User | Password/Notes |
|---------|------|----------------|
| Torrentbox SSH | john | Key auth |
| NAS SSH | pi | Key auth |
| Media Server SSH | pi | Key auth |
| NAS SMB | pi | subterra |
| Deluge | - | subterra |
| PIA VPN | p5674691 | /etc/openvpn/pia-credentials.txt |

---

## Common Commands

### Docker Management
```bash
cd ~/docker
docker compose ps              # Status
docker compose restart         # Restart all
docker compose logs -f sonarr  # View logs
docker compose pull && docker compose up -d  # Update
```

### Mount NAS
```bash
sudo mount -a
```

### Check VPN
```bash
curl ifconfig.me                           # From host
docker exec deluge curl -s ifconfig.me     # From container
```

### Reset Indexers (after VPN reconnect)
```bash
for app in prowlarr sonarr radarr lidarr; do
  docker stop $app
  sqlite3 /home/john/docker/$app/$app.db "DELETE FROM IndexerStatus;"
  docker start $app
done
```

### Fix NAS Permissions
```bash
ssh pi@192.168.10.105 "sudo chmod -R 777 /mnt/media-disk/MediaStorage/Media/TV/"
ssh pi@192.168.10.105 "sudo chmod -R 777 /mnt/media-disk/MediaStorage/Media/Movies/"
```

---

*Updated: January 2026*
