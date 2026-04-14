# Quickstart: VPN Sidecar Migration & Kill-Switch Hardening

**Feature**: 015-vpn-sidecar
**Date**: 2026-04-14
**Purpose**: End-to-end behavioral validation. Doubles as the Test-After harness (Constitution IV).

> **Scope**: Torrentbox Pi 5 (`192.168.10.141`) and HOLYGRAIL (`192.168.10.129`). All commands from the Mac workstation unless noted.

---

## Prerequisites

- [ ] Pre-flight VPN check: `ssh torrentbox "sudo systemctl is-active openvpn@pia"` returns `active`, and `ssh torrentbox "docker exec deluge curl -s --max-time 5 ifconfig.me"` returns a PIA IP (NOT `67.176.27.48`). **Do not begin migration if this fails — 014 left us in a healthy state; if it's broken again, diagnose first.**
- [ ] Mac has `ssh torrentbox` and `ssh holygrail` configured (per `scripts/ssh-config`).
- [ ] `/home/john/docker/` on Torrentbox is at its normal state — confirm with `ssh torrentbox "ls /home/john/docker/"` (expect `deluge, sonarr, radarr, prowlarr, flaresolverr, lidarr, lazylibrarian, docker-compose.yml` plus the `.bak-014-*` snapshots).
- [ ] Known current home WAN IP recorded (needed for the denylist): `curl -s ifconfig.me` from any home LAN device.

---

## US-1 Validation: Sidecar + Kill-Switch

**Goal**: Deluge is fully behind gluetun, kill-switch proven via all five tests in research R5.

### Step 1.1 — Deploy the new Compose

```bash
rsync -av infrastructure/torrentbox/ torrentbox:/home/john/docker-015/
ssh torrentbox "sudo cp /home/john/docker/.env /home/john/docker-015/.env 2>/dev/null || echo 'Create .env manually with PIA creds'"
# If creating manually:
ssh torrentbox "cat > /home/john/docker-015/.env <<EOF
OPENVPN_USER=p1234567
OPENVPN_PASSWORD=<redacted>
EOF
chmod 600 /home/john/docker-015/.env"
```

### Step 1.2 — Graceful cutover

```bash
# Stop the old stack
ssh torrentbox "cd /home/john/docker && docker compose down"
# Disable (not remove) legacy host VPN — will remove in US-4
ssh torrentbox "sudo systemctl stop openvpn@pia"
# Bring up new stack
ssh torrentbox "cd /home/john/docker-015 && docker compose up -d"
sleep 30  # let gluetun establish tunnel
ssh torrentbox "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'gluetun|deluge|sonarr|radarr|prowlarr|flaresolverr'"
```

- [ ] **PASS** if 6+ containers show `Up` with gluetun showing `(healthy)` within 30 seconds.

### Step 1.3 — Kill-switch verification matrix (T1–T5 from research R5)

**T1: Baseline — Deluge routes through PIA**

```bash
ssh torrentbox "docker exec deluge curl -s --max-time 10 https://ifconfig.me"
# Expected: a PIA exit IP (181.41.x.x or similar), NOT 67.176.27.48
```

- [ ] **PASS** → FR-001, FR-002, acceptance scenario US-1.1.

**T2: DNS leak check**

```bash
ssh torrentbox "docker exec deluge sh -c 'apk add bind-tools 2>/dev/null; dig @1.1.1.1 whoami.akamai.net +short'"
# Expected: a PIA-region nameserver IP, not your ISP's DNS
```

- [ ] **PASS**.

**T3: Tunnel killed, sidecar alive → Deluge egress blocked**

```bash
ssh torrentbox "docker exec gluetun pkill -9 wg-quick 2>/dev/null; docker exec gluetun pkill -9 openvpn 2>/dev/null; true"
ssh torrentbox "docker exec deluge curl --max-time 5 https://ifconfig.me"
# Expected: timeout or connection refused. MUST NOT return the home WAN IP.
```

- [ ] **PASS** → FR-004, acceptance scenario US-1.3.

Gluetun will auto-restart the tunnel within ~30s; proceed once `docker exec deluge curl ifconfig.me` returns a PIA IP again.

**T4: Sidecar fully down → Deluge has no egress**

```bash
ssh torrentbox "docker stop gluetun"
ssh torrentbox "docker exec deluge curl --max-time 5 https://ifconfig.me; echo EXIT=$?"
# Expected: "network is unreachable" / "could not resolve host" / non-zero exit. MUST NOT return the home WAN IP.
ssh torrentbox "docker start gluetun"; sleep 20
```

- [ ] **PASS** → FR-004, acceptance scenario US-1.2, SC-002.

**T5: NetworkMode sanity (catches the silent-bridge leak trap)**

```bash
ssh torrentbox "docker inspect deluge | jq '.[0].HostConfig.NetworkMode'"
# Expected: "container:<gluetun container id>" — NOT "default" or a bridge name
```

- [ ] **PASS** → FR-002, research R5 pitfall avoided.

### Step 1.4 — End-to-end pipeline still works

Trigger a test grab through Sonarr or Radarr:

1. Pick an existing series, request an episode manually.
2. Confirm Deluge receives it (appears in Web UI at `http://192.168.10.141:8112`).
3. Confirm it downloads, moves to `/mnt/nas/torrents/complete`, and gets imported by Sonarr.

- [ ] **PASS** → FR-007, acceptance scenario US-1.4.

### Step 1.5 — LAN reachability preserved

```bash
curl -s --max-time 5 http://192.168.10.141:8112 | head -c 100  # Deluge Web UI
curl -s --max-time 5 http://192.168.10.141:8989/api/v3/system/status -H "X-Api-Key: ebb7706d9d7f4401939338bab7ebc103" | jq .version  # Sonarr
```

- [ ] **PASS** → FR-008.

---

## US-2 Validation: Watchdog (Advisor rule)

**Goal**: Advisor's new `vpn_leak` rule detects simulated leaks, emits alerts, and escalates to auto-stop after 3 strikes.

### Step 2.1 — New rule registered and probe running

```bash
curl -sSH "Content-Type: application/json" http://advisor.holygrail/api/rules | jq '.[] | select(.id=="vpn_leak")'
# Expected: returns rule metadata
```

- [ ] **PASS** if rule is registered.

### Step 2.2 — Synthetic green-state heartbeat visible

```bash
curl -s http://advisor.holygrail/api/health-checks?service=deluge-vpn | jq '.[0] | {checked_at, status, details}'
# Expected: status=green, observed_ip = a PIA IP, recent timestamp
```

- [ ] **PASS** → FR-013 (heartbeat observable).

### Step 2.3 — Simulated leak detection

Temporarily stop gluetun so the probe sees Deluge returning no response (yellow soft warning — verify distinct from leak):

```bash
ssh torrentbox "docker stop gluetun"
# Wait for next probe cycle (≤15 min)
# Check Advisor
curl -s http://advisor.holygrail/api/health-checks?service=deluge-vpn | jq '.[0] | {status, details}'
# Expected: status=yellow (probe unreachable), NOT red
curl -s http://advisor.holygrail/api/alerts?rule_id=vpn_leak | jq '.items | length'
# Expected: 0 new alerts from this yellow state (FR-014)
ssh torrentbox "docker start gluetun"; sleep 30
```

- [ ] **PASS** → FR-014 (soft warning, not a leak alert).

Next, simulate a real leak by adding a *wrong* entry to the denylist to force a match against the current PIA IP:

```bash
# Get current PIA exit IP
CURRENT_IP=$(ssh torrentbox "docker exec deluge curl -s ifconfig.me")
# Add it to the denylist (temporarily)
curl -sSH "Content-Type: application/json" -X PUT http://advisor.holygrail/api/thresholds/vpn_leak \
  -d "{\"denylist_ips\": [\"67.176.27.48\", \"$CURRENT_IP\"]}"
# Wait for next probe (≤15 min)
curl -s http://advisor.holygrail/api/alerts?rule_id=vpn_leak | jq '.items[] | {message, severity, created_at}'
# Expected: 1 new critical alert
```

- [ ] **PASS** → FR-010, FR-011, SC-004.

### Step 2.4 — Escalation + auto-stop after 3 strikes

Keeping the spoofed denylist from Step 2.3, wait for 3 consecutive leak probes (~45 min at default 15-min interval) OR manually advance the rule engine 3 times.

```bash
ssh torrentbox "docker ps -a --format '{{.Names}} {{.Status}}' | grep deluge"
# Expected after 3rd strike: deluge status = "Exited"
curl -s http://advisor.holygrail/api/alerts?rule_id=vpn_leak:remediation | jq '.items[0].message'
# Expected: "Auto-stopped Deluge after 3 consecutive leak detections (latest IP: ...)"
```

- [ ] **PASS** → FR-012, Clarification Q2, acceptance scenario US-2.4.

**Cleanup**: revert the denylist to the legitimate home-WAN-only entry, restart Deluge:

```bash
curl -sSH "Content-Type: application/json" -X PUT http://advisor.holygrail/api/thresholds/vpn_leak \
  -d '{"denylist_ips": ["67.176.27.48"]}'
ssh torrentbox "docker start deluge"
```

### Step 2.4a — VPN status prominently surfaced (FR-013, US-2 AS-5/6/7)

Open the Advisor dashboard at `http://advisor.holygrail/` (or equivalent).

- [ ] Top-of-dashboard **VPN Status card** is visible, green, showing `Tunnel up · exit <PIA IP> · probed <time> ago`.
- [ ] Top-nav status pill reads `VPN · OK` in green.
- [ ] Endpoint sanity: `curl -s http://advisor.holygrail/api/vpn-status | jq .` returns `state="OK"`, non-null `observed_ip` (PIA range), recent `last_probe_at`, `active_alert_id=null`.

Now force the state transitions:

```bash
# Force LEAK_DETECTED: temporarily add current PIA exit IP to denylist (from Step 2.3 spoof)
# After ≤ 1 check interval
curl -s http://advisor.holygrail/api/vpn-status | jq '{state, observed_ip, active_alert_id, message}'
# Expected: state=LEAK_DETECTED, active_alert_id is a number
```

- [ ] Dashboard card turns red, shows observed IP + "View alert" link that resolves to the fired `vpn_leak` alert.
- [ ] Top-nav pill switches to `VPN · ⚠ LEAK` within one check interval (US-2 AS-6).
- [ ] Revert denylist per Step 2.3 cleanup; card returns to green within one interval.

### Step 2.4b — AUTO_STOPPED state rendering

After the 3-strike escalation in Step 2.4 fires (before the cleanup):

- [ ] `curl -s http://advisor.holygrail/api/vpn-status | jq .state` returns `"AUTO_STOPPED"`.
- [ ] Dashboard card shows the red "Deluge stopped by auto-remediation" state with a remediation action badge.

### Step 2.5 — Watchdog-down detectability

```bash
# Stop the rule engine / probe path temporarily (Phase 2 will define the exact mechanism; likely disabling the rule via UI)
# Wait > 2 check intervals
# Inspect dashboard
```

- [ ] **PASS** if the absence of heartbeats for ≥ 2 intervals shows as a distinct "watchdog down" indicator → FR-013, SC-005.

---

## US-3 Validation: PIA port forwarding

**Goal**: PIA-assigned port is propagated into Deluge's live `listen_ports`; inbound peer count becomes non-zero.

### Step 3.1 — Forwarded port visible from gluetun

```bash
ssh torrentbox "docker exec gluetun cat /tmp/gluetun/forwarded_port 2>/dev/null || \
  docker exec gluetun wget -qO- http://localhost:8000/v1/openvpn/portforwarded"
# Expected: integer port number
```

- [ ] **PASS** → FR-015, acceptance scenario US-3.1.

### Step 3.2 — Port pushed into Deluge config

```bash
ssh torrentbox "docker exec deluge deluge-console -c /config 'config listen_ports'"
# Expected: (P, P) where P == the value from Step 3.1
ssh torrentbox "docker exec deluge deluge-console -c /config 'config random_port'"
# Expected: False
```

- [ ] **PASS** → FR-016, acceptance scenario US-3.2.

### Step 3.3 — Inbound peers materialize (24-hour check)

Add a healthy public torrent (e.g., a recent Linux ISO). Leave it seeding for 24 hours.

```bash
ssh torrentbox "docker exec deluge deluge-console -c /config 'info' | head -40"
# Expected: at least one torrent shows Peers > 0 with the connected peer list
```

- [ ] **PASS** → FR-018, SC-006, acceptance scenario US-3.3.

### Step 3.4 — Rotation handled automatically

Harder to observe live (PIA rotates every ~60 days). Observational only:

- [ ] **DEFERRED TO T+60d**: At rotation time, confirm `listen_ports` updates within minutes of the rotation event, no manual intervention. → FR-017, SC-007.

---

## US-4 Validation: Legacy decommission (only after 7 days stable)

**Goal**: Host-level `openvpn@pia` archived; host iptables clean.

**Gate**: US-1 through US-3 have been stable for ≥ 7 consecutive days with zero watchdog alerts.

### Step 4.1 — Disable the legacy service

```bash
ssh torrentbox "sudo systemctl disable --now openvpn@pia && sudo systemctl is-enabled openvpn@pia"
# Expected: "disabled"
```

- [ ] **PASS** → FR-019.

### Step 4.2 — Archive the config

```bash
ssh torrentbox "sudo mkdir -p /etc/openvpn/legacy-014 && sudo mv /etc/openvpn/pia.conf /etc/openvpn/vpn-up.sh /etc/openvpn/vpn-up.sh.bak-014-* /etc/openvpn/vpn-down.sh /etc/openvpn/pia-credentials.txt /etc/openvpn/legacy-014/"
ssh torrentbox "sudo ls /etc/openvpn/legacy-014/"
```

- [ ] **PASS** → FR-020.

### Step 4.3 — Host iptables clean

```bash
ssh torrentbox "sudo iptables -L OUTPUT -n --line-numbers | head -5; echo '---'; sudo iptables -L INPUT -n --line-numbers | head -5"
# Expected: both chains show "policy ACCEPT" with zero explicit rules
```

- [ ] **PASS** → FR-021, SC-008.

### Step 4.4 — Docs updated

```bash
grep -n "openvpn@pia" /Users/jd/Code/camelot/docs/INFRASTRUCTURE.md
# Expected: if present, only in a "Historical (decommissioned)" footnote
```

- [ ] **PASS** → FR-022.

---

## Rollback (within 7 days, per FR-026)

If US-1 or US-2 reveals an unresolvable issue:

```bash
ssh torrentbox "cd /home/john/docker-015 && docker compose down"
ssh torrentbox "sudo systemctl start openvpn@pia"
ssh torrentbox "cd /home/john/docker && docker compose up -d"
# Verify
ssh torrentbox "docker exec deluge curl -s ifconfig.me"
# Expected: PIA IP via the legacy path
```

- [ ] **PASS** if reversion completes in under 60 min and Deluge routes through the legacy tunnel → SC-009.

---

## Cross-cutting validation

### No committed credentials

```bash
git grep -iE 'OPENVPN_USER|OPENVPN_PASSWORD|passkey' -- infrastructure/torrentbox/ docs/ specs/015-vpn-sidecar/ || echo "no creds committed"
```

- [ ] **PASS** → FR-006.

### `infrastructure/torrentbox/` is repo-reproducible

```bash
ls -la /Users/jd/Code/camelot/infrastructure/torrentbox/
# Expected: docker-compose.yml, .env.example, gluetun-port-hook.sh, README.md
```

- [ ] **PASS** → FR-023.

### Memory updated

```bash
grep "RESOLVED" /Users/jd/.claude/projects/-Users-jd-Code-camelot/memory/project_vpn_incident_2026-04.md
```

- [ ] **PASS** if the memory reflects the current resolution status post-US-4.

---

## Notes

- Steps 1.3 T3 and T4 temporarily break Deluge's egress; normal auto-recovery takes ≤60s after gluetun is back. Do not run during an active download window.
- Step 2.4 deliberately stops Deluge to prove auto-stop works. Acceptable disruption; Deluge comes back with a single `docker start deluge` after the cleanup step.
- Step 3.3 requires 24h of patience; schedule the run accordingly.
- Step 3.4 is T+60d observational — mark as deferred at initial landing.
- US-4 is explicitly gated on 7 days of stability. Do not execute on the same day as US-1 / US-2 / US-3.
