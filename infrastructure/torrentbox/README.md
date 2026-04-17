# Torrentbox infrastructure (`infrastructure/torrentbox/`)

Repo-committed Compose for the Torrentbox Pi 5 (192.168.10.141). Source of truth for the torrent stack — gluetun VPN sidecar, Deluge piggybacking on its netns, and the *arr ecosystem on the default network.

## Files

| File | Purpose | Committed? |
| ---- | ------- | ---------- |
| `docker-compose.yml` | Service definitions for the Pi | Yes |
| `.env.example` | PIA credential template | Yes |
| `gluetun-port-hook.sh` | Gluetun → Deluge state sync (PIA forwarded port + tun0 IP) | Yes |
| `.env` | Real PIA credentials | NO — Pi only, gitignored |

## First-time deploy (cutover from legacy host-OpenVPN)

Prerequisites:

- 014's VPN fix is in place (`openvpn@pia` is currently active and Deluge routes through PIA — verify via `ssh torrentbox "docker exec deluge curl -s ifconfig.me"`).
- Snapshot of the existing `/home/john/docker/` directory exists for rollback.
- PIA credentials on hand.

Steps:

```bash
# 1. Snapshot live state on the Pi (rollback target)
ssh torrentbox "sudo cp -a /home/john/docker /home/john/docker.bak-015-$(date +%Y%m%d)"

# 2. Stop the legacy stack (Deluge briefly offline)
ssh torrentbox "cd /home/john/docker && docker compose down"
ssh torrentbox "sudo systemctl stop openvpn@pia"

# 3. Overlay the new Compose + hook script into the live path
#    (existing config dirs deluge/ sonarr/ radarr/ ... are preserved)
rsync -av --exclude='.env' infrastructure/torrentbox/ torrentbox:/home/john/docker/

# 4. Create real .env on the Pi (credentials only on the Pi, never in repo)
ssh torrentbox 'cat > /home/john/docker/.env <<EOF
OPENVPN_USER=<from password manager>
OPENVPN_PASSWORD=<from password manager>
EOF
chmod 600 /home/john/docker/.env'

# 5. Persistent gluetun state directory (critical — 60-day PIA PF token survives restarts here)
ssh torrentbox "mkdir -p /home/john/docker/gluetun && chmod 700 /home/john/docker/gluetun"

# 6. Bring up the new stack
ssh torrentbox "cd /home/john/docker && docker compose up -d"
sleep 45  # let gluetun establish tunnel

# 7. Verify gluetun is healthy
ssh torrentbox "docker ps --filter name=gluetun --format '{{.Status}}'"
# Expected: "Up N seconds (healthy)"

# 8. Run the kill-switch verification matrix (specs/015-vpn-sidecar/quickstart.md Step 1.3 T1-T5)
# T1: Deluge external IP is PIA, not home WAN
# T2: DNS resolves via VPN, not ISP
# T3: Kill tunnel inside gluetun → Deluge has no egress
# T4: Stop gluetun → Deluge has no egress
# T5: docker inspect deluge → NetworkMode = container:<gluetun-id>
```

After 7 days of stable operation with zero `vpn_leak` alerts, decommission the legacy host OpenVPN per `specs/015-vpn-sidecar/tasks.md` Phase 6 (T046–T052).

## Rollback (within 7 days, per FR-026)

```bash
ssh torrentbox "cd /home/john/docker && docker compose down"
ssh torrentbox "sudo mv /home/john/docker /home/john/docker.failed-015 && sudo mv /home/john/docker.bak-015-* /home/john/docker"
ssh torrentbox "sudo systemctl start openvpn@pia"
ssh torrentbox "cd /home/john/docker && docker compose up -d"
ssh torrentbox "docker exec deluge curl -s ifconfig.me"  # should be a PIA IP via legacy path
```

Target: under 60 minutes from decision to verified-working.

## Image-tag discipline

`docker-compose.yml` pins `qmcgaw/gluetun:v3.40.0`. Do NOT bump to `:latest`. Read the gluetun CHANGELOG before any version bump — env vars get renamed in major releases (the 014 incident class for system-wide breakage). The other linuxserver images are still on `:latest` historically; tightening those is a future hygiene PR, not in scope here.

## Common operations

```bash
# View gluetun logs (PIA tunnel + port-forwarding events)
ssh torrentbox "docker logs gluetun --tail 50"

# Inspect Deluge's current listen_ports (should match the PIA-forwarded port)
ssh torrentbox "docker exec deluge deluge-console -c /config 'config listen_ports'"

# Manually trigger the port hook (for testing)
ssh torrentbox "docker exec gluetun /gluetun-scripts/gluetun-port-hook.sh 12345"

# Verify Deluge's external IP is still a PIA exit
ssh torrentbox "docker exec deluge curl -s ifconfig.me"
```

## Architecture notes

- **Kill-switch**: enforced inside gluetun's netns via `FIREWALL=on`. Default-deny outbound except to LAN (192.168.10.0/24) and the VPN tunnel itself. If gluetun stops or the tunnel drops, Deluge's egress drops to zero — verifiable by stopping gluetun and observing `docker exec deluge curl --max-time 5 ifconfig.me` time out.
- **Inbound peers**: routed through PIA's port forwarding. `random_port=False`, `listen_ports=(P,P)`, and `listen_interface=<tun0 IP>` are all set by the hook script (`gluetun-port-hook.sh`). The `listen_interface` sync is required because libtorrent's `expand_unspecified_address()` skips POINTOPOINT interfaces, so leaving `listen_interface` empty or `0.0.0.0` makes Deluge bind only to the docker bridge and miss tun0 entirely.
- **Hook script Docker socket access**: the hook runs `docker exec deluge deluge-console ...`, which requires the Docker socket bind-mounted into gluetun. Tradeoff documented in `specs/015-vpn-sidecar/research.md` R3 — accepted to avoid a secondary watcher container.
- **Watchdog**: a separate Advisor rule (`vpn_leak`) on HOLYGRAIL probes Deluge's external IP every cycle and auto-stops Deluge after 3 consecutive leak detections. Configured via the Advisor backend, not via this Compose file.

## Related docs

- Spec: [`specs/015-vpn-sidecar/spec.md`](../../specs/015-vpn-sidecar/spec.md)
- Plan + research: [`specs/015-vpn-sidecar/plan.md`](../../specs/015-vpn-sidecar/plan.md), [`research.md`](../../specs/015-vpn-sidecar/research.md)
- Quickstart validation: [`specs/015-vpn-sidecar/quickstart.md`](../../specs/015-vpn-sidecar/quickstart.md)
- Incident background: [`project_vpn_incident_2026-04` memory](../../../.claude/projects/-Users-jd-Code-camelot/memory/project_vpn_incident_2026-04.md)
