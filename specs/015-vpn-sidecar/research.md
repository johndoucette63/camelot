# Phase 0 Research: VPN Sidecar Migration & Kill-Switch Hardening

**Feature**: 015-vpn-sidecar
**Date**: 2026-04-14
**Purpose**: Resolve every open decision before design. Each entry: Decision + Rationale + Alternatives.

---

## R1. Sidecar VPN image selection

**Decision**: **`qmcgaw/gluetun`**, pinned to a specific tag (initial target: `v3.40.0` or the latest known-stable as of implementation day).

**Rationale**:

- Only actively-maintained (monthly releases through 2026), sidecar-first VPN container with first-class PIA support.
- Default-deny iptables firewall is built in and cannot be disabled at runtime — matches FR-003/FR-004 literally.
- Native PIA port forwarding with automatic token refresh (matches FR-015/FR-017).
- Multi-arch image including arm64 (Pi 5 compatible).
- Structured logs with controllable verbosity (`LOG_LEVEL=info`), no credential leakage at default levels (FR-006).

**Alternatives considered and rejected**:

- `dperson/openvpn-client` — largely stale, reports of UDP packet loss that disappear under gluetun, no PIA port forwarding.
- `haugene/transmission-openvpn` — bundles Transmission; wrong shape (would require ripping Transmission out while keeping our Deluge).
- `binhex/arch-delugevpn` — bundles Deluge inside the VPN container. Viable but gives up the sidecar-pattern flexibility (one container for Deluge, another for VPN — easier to migrate either independently in future).

**Implementation constraints derived from this choice**:

- Deluge must declare `network_mode: "service:gluetun"` and omit `networks:`.
- Deluge ports (`8112`, `58846`) must be published on the **gluetun** service, not Deluge (otherwise Docker attaches a bridge interface and bypasses the kill-switch).
- `cap_add: [NET_ADMIN]` and `devices: [/dev/net/tun]` on gluetun.

---

## R2. VPN protocol — WireGuard vs OpenVPN

**Decision**: **WireGuard via gluetun's native PIA provider mode** (`VPN_SERVICE_PROVIDER=private internet access`, `VPN_TYPE=wireguard`).

**Rationale**:

- Lower CPU overhead than OpenVPN — material on Pi-class hardware, preserves headroom for the *arr stack + Deluge under load.
- Faster reconnect after network hiccups (<100ms vs multi-second OpenVPN handshake).
- PIA port forwarding works reliably with gluetun's native WireGuard path (contrasts with **broken** `custom` WireGuard + PF — see gluetun issues #2320, #2646, #3070).
- Community consensus as of 2025-2026 favours WireGuard via gluetun native for Pi-class sidecar use.

**Alternatives considered and rejected**:

- **OpenVPN via gluetun native** — slower, higher CPU, but proven. Kept as a fallback lever: if WG + PF misbehaves in practice on our PIA region, flip `VPN_TYPE=openvpn` and re-test. Not the initial target.
- **Custom WireGuard config** — explicitly broken when combined with PF on current gluetun; would require maintaining our own `wg0.conf`.
- **Continue legacy host-level OpenVPN** — rejected; the whole feature exists to get rid of this topology.

**Follow-up risk**: WireGuard sessions on PIA can silently expire (tracked by third-party `ccarpinteri/pia-wg-refresh`). gluetun's healthcheck + restart policy covers most cases; our watchdog covers the edge case (stale session presenting as wrong IP).

---

## R3. PIA port forwarding → Deluge `listen_ports` propagation

**Decision**: Use **`VPN_PORT_FORWARDING_UP_COMMAND`** with the `{{PORT}}` template to invoke a small bash script that runs `deluge-console config --set listen_ports (P,P)` inside the deluge container via `docker exec`.

**Rationale**:

- `VPN_PORT_FORWARDING_UP_COMMAND` is gluetun's forward-compatible mechanism (the `/tmp/gluetun/forwarded_port` file is deprecated in v4.0 — avoid relying on it).
- Template substitution (`{{PORT}}`, `{{PORTS}}`, `{{VPN_INTERFACE}}`) is cleanly documented and robust across gluetun versions.
- `deluge-console config --set listen_ports (P,P)` updates the **live** daemon state — no Deluge restart, no interruption to in-flight downloads.
- Pair with a bootstrap step that sets `random_port=false` once; thereafter, Deluge always listens on the PIA-assigned port.
- Persist gluetun's working directory (`/gluetun` bind-mounted to `/home/john/docker/gluetun/`) so the 60-day PIA PF token survives container restarts; without persistence, gluetun re-requests on every start and can hit rate limits (gluetun issue #930).

**Alternatives considered and rejected**:

- **Shared-file watcher** (`inotifywait` on `/tmp/gluetun/forwarded_port`) — works today, deprecated tomorrow.
- **In-gluetun cron** — fragile, doesn't react to rotation events.
- **Manual port entry** — violates FR-016 (must be automatic).

**Implementation notes**:

- The hook script needs network access from inside gluetun's namespace to reach `deluge-console`. Simplest: the script runs on the **host** via `docker exec deluge deluge-console ...`, with gluetun invoking it via the host's docker socket. This requires mounting the Docker socket into gluetun (standard pattern, security-aware). **Decision to defer to implementation**: evaluate whether mounting the socket is acceptable vs running the hook as a separate tiny container that watches gluetun's output. Default: host-script path; escalate if it smells wrong during implementation.

**Concrete fallback (if the primary hook path fails)** — fully pre-designed so T041 is implementation, not design:

- Add a host-side poller at `/home/john/docker/gluetun-port-poller.sh` invoked by a systemd timer every 60 seconds.
- Script body:

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  PORT_FILE=/home/john/docker/gluetun/forwarded_port
  STATE_FILE=/home/john/docker/.last-forwarded-port
  [ -f "$PORT_FILE" ] || exit 0
  NEW_PORT=$(cat "$PORT_FILE")
  OLD_PORT=$(cat "$STATE_FILE" 2>/dev/null || echo "")
  [ "$NEW_PORT" = "$OLD_PORT" ] && exit 0
  echo "$(date -Is) port change: $OLD_PORT -> $NEW_PORT" >> /var/log/gluetun-port-poller.log
  docker exec deluge deluge-console -c /config "config --set listen_ports ($NEW_PORT,$NEW_PORT)"
  docker exec deluge deluge-console -c /config "config --set random_port False"
  echo "$NEW_PORT" > "$STATE_FILE"
  ```

- Systemd timer: `/etc/systemd/system/gluetun-port-poller.timer` with `OnActiveSec=30s`, `OnUnitActiveSec=60s`.
- Service unit: `/etc/systemd/system/gluetun-port-poller.service` invoking the script.
- Activation: `sudo systemctl enable --now gluetun-port-poller.timer`.
- **Known limitation**: depends on gluetun writing `/tmp/gluetun/forwarded_port`, which is deprecated in gluetun v4.0 (R6). If gluetun is upgraded past v4.0, switch the poller source to `curl http://localhost:<gluetun-control-port>/v1/openvpn/portforwarded` instead — trivial one-line change.
- **Trade-off**: 60-second lag from PIA rotation to Deluge listen-port update (vs near-instant with the primary hook). Acceptable — PIA rotations are 60-day events, not 60-second events.

---

## R4. Docker Compose ordering + healthchecks

**Decision**:

- gluetun service uses a **custom healthcheck** that actually probes external connectivity (e.g., `wget -qO- https://ipinfo.io/ip`) rather than gluetun's minimal stock check, with `interval=30s, timeout=10s, retries=3, start_period=30s`.
- deluge service declares both `network_mode: "service:gluetun"` and **`depends_on: { gluetun: { condition: service_healthy } }`** — the latter is required because `network_mode: service:X` implicitly waits for *started*, not *healthy*.
- Both services use `restart: unless-stopped`.
- Drop the legacy `HEALTH_VPN_DURATION_INITIAL` env var if it appears in any copied-from-elsewhere examples (removed on current gluetun, gluetun issue #2894).

**Rationale**: Pattern is standard and well-documented. The custom healthcheck matters — gluetun's default check has been known to produce false positives that cause restart loops (gluetun issues #2942, #3021, #3069).

**Alternatives considered**:

- Rely on gluetun's stock healthcheck — rejected due to known false-positive flap loops.
- Use a sidecar "wait-for" container — over-engineered; Compose native `depends_on.condition` does the job.

**Pi 5 / Debian Trixie gotchas captured from research**:

- Enable `cgroup_memory=1 cgroup_enable=memory` in `/boot/firmware/cmdline.txt` if Docker health resource limits are used.
- Host must load `iptable_mangle` and `iptable_nat` — gluetun bundles its own iptables binaries (iptables-legacy) inside the container, but kernel modules still need to be loadable host-side.
- Disable IPv6 within gluetun unless explicitly handled — dual-stack leaks are trivial.

---

## R5. Kill-switch verification matrix

**Decision**: Adopt a **five-test verification matrix** as the deterministic proof that the kill-switch actually works. Every test is scriptable; all five run in `quickstart.md` under US-1.

| Test | Action | Expected |
|------|--------|----------|
| T1 | `docker exec deluge curl -s https://ifconfig.me` | Returns PIA exit IP, not home WAN |
| T2 | `docker exec deluge dig @1.1.1.1 whoami.akamai.net` (DNS leak check) | Resolves via VPN DNS, not ISP DNS |
| T3 | `docker exec gluetun killall openvpn` OR `wg-quick down wg0` (tunnel killed, sidecar alive) | Deluge `curl --max-time 5 ifconfig.me` times out (no fallback) |
| T4 | `docker stop gluetun` (sidecar fully down) | Deluge egress fails entirely (network unreachable) |
| T5 | `docker inspect deluge \| jq '.[0].HostConfig.NetworkMode'` | Returns `container:<gluetun-id>`, never `default` or anything bridge-ish |

**Rationale**: T5 catches the **single most common silent-leak cause** — declaring `networks:` alongside `network_mode: service:gluetun` reverts Deluge to the default bridge silently (documented Compose bug). The rest prove the firewall holds under each failure axis.

**Alternatives considered**:

- Trusting gluetun's `FIREWALL=on` — rejected; the spec requires verifiable kill-switch behavior, not a claim.

**Pitfalls to actively avoid in configuration**:

- Setting `FIREWALL_OUTBOUND_SUBNETS` wider than `192.168.10.0/24` (e.g., `0.0.0.0/0`) — effectively disables the kill-switch.
- Publishing Deluge ports on the deluge service — forces Docker to attach a bridge, bypassing gluetun entirely.

---

## R6. Known gluetun issues and upgrade hygiene

**Decision**: **Pin the gluetun tag explicitly** (not `:latest`), read the gluetun CHANGELOG before every bump, persist `/gluetun` bind-mount, use `VPN_SERVICE_PROVIDER=private internet access` (native), not `custom`.

**Tracked issues to stay aware of**:

- `#2894` — `HEALTH_VPN_DURATION_INITIAL` removed; bare upgrades from old configs break startup.
- `#2942 / #3021 / #3069` — healthcheck false-positive flap loops; mitigated by the custom external-IP healthcheck (R4).
- `#2823` — healthcheck's built-in DNS resolution through the tunnel can be slow; set `HEALTH_TARGET_ADDRESS=1.1.1.1:443`.
- `#2320 / #2646 / #3070` — PIA + WG + `custom` provider + PF combo broken; **use native provider only** (already baked into R2).
- `#2710` — intermittent "no forwarded port being fetched" with PIA OpenVPN; mitigated by persistent `/gluetun` dir (R3).
- `#930` — 403 on token refresh if PIA rate-limits the IP (from repeated restarts without persistence) — mitigated by persistence.
- File `/tmp/gluetun/forwarded_port` deprecated in v4.0 — use the command hook, not the file.

**Alternatives considered**: Pinning to SHA digest instead of tag — more rigorous but harder to read; tag-pin is the pragmatic default.

---

## R7. Watchdog host — Torrentbox cron vs HOLYGRAIL Advisor rule

**Decision**: Run the watchdog **on HOLYGRAIL as a new Advisor rule** (`vpn_leak`), with the probe sourced by a new health-check module `deluge_external_ip.py` writing to the existing `HealthCheckResult` table. Alerts flow through the existing `Alert` pipeline established in Phase 4.5.

**Rationale**:

- **External vantage point**: a watchdog running on the same host it's watching can't tell "the host is down" from "the host is leaking." Running on HOLYGRAIL gives a separate observer. If Torrentbox itself is off, the rule fires a distinct "health-check probe unreachable" signal (matching FR-014's soft-warning requirement) instead of silent absence.
- **Reuse, not reinvent**: Phase 4.5 already has `Alert`, `AlertThreshold`, `NotificationSink`, ack/resolve semantics, retention, a rule engine, and UI. The feature becomes one new `Rule` subclass + one new health-check source + one test file. Duplicating any of that as a Torrentbox cron would violate Constitution II.
- **Heartbeat is free**: the Advisor rule engine's scheduled runs naturally produce a heartbeat (FR-013 — "watchdog's last successful run timestamp MUST be surfaced"). No new observability surface needed.
- **Remediation path**: the 3-strike auto-stop (FR-012 / Clarification Q2) needs to issue `docker stop deluge` on Torrentbox. The Advisor already uses `docker-py` to talk to remote Docker daemons for other features; extending that to a stop action on a specific container is one function call.

**Alternatives considered and rejected**:

- **Torrentbox-side cron** running bash + curl — simpler but duplicates alert delivery, lacks external observation, no UI integration.
- **Grafana alert** querying InfluxDB — possible (InfluxDB already runs on HOLYGRAIL) but requires a new InfluxDB write path from Torrentbox plus Grafana alert config. More moving parts; Advisor rule is more idiomatic per Phase 4.5.
- **Both (defense in depth)** — rejected for scope. The Advisor rule is sufficient; if a belt-and-suspenders watchdog is later wanted, it can be added without conflict.

**Implementation notes**:

- The health-check source probes Deluge's Web API on the Pi (e.g., a small endpoint that returns `curl ifconfig.me` from inside the deluge container) or calls the Docker API remotely to run `docker exec deluge curl ifconfig.me`. Exact mechanism is a Phase 2 tasks-level decision; the contract (ExternalIP observed vs denylist) is unchanged.
- Rule runs on the existing rule-engine schedule (≤15 min per FR-010; confirm current Advisor schedule meets this).
- Remediation is a new `RuleAction` concept (current Advisor rules only emit alerts). Implementation: extend the rule engine to support an `on_escalate` action for rules that want auto-remediation, gated by a `remediation_enabled` column on the rule's threshold row (off by default in code, turned on for this rule via config).

---

## R8. Migration + rollback mechanics

**Decision**: Execute the migration in one sitting with a documented rollback path.

**Forward procedure**:

1. Author `infrastructure/torrentbox/docker-compose.yml` + `.env.example` + `gluetun-port-hook.sh` + `README.md` in-repo.
2. Rsync to Torrentbox under `/home/john/docker-014/` (parallel path — not overwriting the live `/home/john/docker/docker-compose.yml` yet).
3. Create `.env` on the Pi at `/home/john/docker-014/.env` (gitignored, PIA creds only).
4. `docker compose -f /home/john/docker-014/docker-compose.yml up -d` — brings up gluetun + deluge + the other *arr containers on the new Compose file. Requires stopping the old `docker compose` stack first.
5. Run kill-switch verification matrix (R5 T1–T5).
6. Swap live path: move old `/home/john/docker/` → `/home/john/docker.bak-015/`, move `/home/john/docker-014/` → `/home/john/docker/`.

**Rollback procedure** (if issues in first 7 days, per FR-026):

1. `docker compose -f /home/john/docker/docker-compose.yml down`.
2. Restore `/home/john/docker/` from `/home/john/docker.bak-015/`.
3. `docker compose up -d`.
4. `sudo systemctl start openvpn@pia` to re-enable host-level VPN.
5. Verify Deluge routes through `tun0` again via the legacy path.
6. Target: <60 min from decision to verified-working (SC-009).

**Rationale**: Parallel-path cutover minimizes the window where either stack is in an indeterminate state. Full Compose-file replacement (not in-place edit) keeps the rollback blob self-contained.

---

## Resolved NEEDS CLARIFICATION

- Sidecar image → gluetun (R1)
- Protocol → WireGuard native (R2)
- Port-forwarding → `VPN_PORT_FORWARDING_UP_COMMAND` → `deluge-console` (R3)
- Watchdog host → HOLYGRAIL Advisor rule (R7)
- Leak detection policy → denylist, home WAN IP minimum (Clarification Q1)
- Auto-remediation → stop Deluge after 3 consecutive leaks (Clarification Q2)

None outstanding.
