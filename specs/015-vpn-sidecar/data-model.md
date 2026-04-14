# Phase 1 Data Model: VPN Sidecar Migration & Kill-Switch Hardening

**Feature**: 015-vpn-sidecar
**Date**: 2026-04-14

No new database tables. The feature reuses the existing Advisor schema (Phase 4.5) and introduces one new in-process rule plus one new health-check source. The "data model" below describes configuration shapes and one new row category in an existing table.

---

## E1. Gluetun Sidecar Configuration

**Lives in**: `infrastructure/torrentbox/docker-compose.yml` (repo) + `/home/john/docker/.env` (Pi, gitignored).
**Surface**: Docker Compose service definition + env vars passed to the gluetun container.

### Fields (Compose `gluetun` service)

| Field | Value | Source |
|-------|-------|--------|
| `image` | `qmcgaw/gluetun:<pinned-tag>` (e.g., `v3.40.0`) | Compose, version-controlled |
| `container_name` | `gluetun` | Compose |
| `cap_add` | `[NET_ADMIN]` | Compose (required for tunnel interface creation) |
| `devices` | `[/dev/net/tun:/dev/net/tun]` | Compose |
| `restart` | `unless-stopped` | Compose |
| `volumes` | `- /home/john/docker/gluetun:/gluetun` | Persistence for PIA PF token and session state (research R3) |
| `ports` | `[8112:8112, 58846:58846]` (Deluge's ports — published HERE, not on deluge service) | Compose |
| `healthcheck` | `test: ["CMD", "wget", "-qO-", "https://ipinfo.io/ip"]; interval=30s; timeout=10s; retries=3; start_period=30s` | Compose (custom, overrides stock) |
| `env_file` | `[/home/john/docker/.env]` | Pi-only, gitignored |
| **env vars via .env** | — | — |
| `VPN_SERVICE_PROVIDER` | `private internet access` | Native provider mode, not `custom` |
| `VPN_TYPE` | `wireguard` | Per research R2 |
| `OPENVPN_USER` / `OPENVPN_PASSWORD` | PIA credentials | Same creds used for both WG and OVPN |
| `SERVER_REGIONS` | `US Denver` (or operator's preferred region) | Matches current setup |
| `VPN_PORT_FORWARDING` | `on` | FR-015 |
| `VPN_PORT_FORWARDING_PROVIDER` | `private internet access` | |
| `VPN_PORT_FORWARDING_UP_COMMAND` | `/gluetun-scripts/gluetun-port-hook.sh {{PORT}}` | FR-016 |
| `FIREWALL` | `on` (default — do not override) | FR-003 |
| `FIREWALL_OUTBOUND_SUBNETS` | `192.168.10.0/24` | Explicit LAN allow; must NOT be wider (research R5 pitfall) |
| `LOG_LEVEL` | `info` | FR-006 — avoids credential leakage |
| `HEALTH_TARGET_ADDRESS` | `1.1.1.1:443` | Research R6 — avoids DNS-dependent flap loop |

### Validation rules (from Requirements)

- `image` pinned, not `:latest` (FR-005).
- `.env` file gitignored and never committed (FR-006).
- `FIREWALL_OUTBOUND_SUBNETS` must be ≤ LAN scope; no `0.0.0.0/0` (research R5 pitfall; FR-003 defense).
- `ports` block must be on gluetun, not deluge (research R5; FR-004).

---

## E2. Deluge Container (Modified)

**Lives in**: `infrastructure/torrentbox/docker-compose.yml`.

### Changes from current state

| Field | Before | After |
|-------|--------|-------|
| `network_mode` | (unset → default bridge) | `"service:gluetun"` |
| `networks:` | (unset) | MUST remain unset (research R5 — declaring this silently reverts to bridge) |
| `ports` | `[8112:8112, 58846:58846, 6881:6881, 6881:6881/udp]` | REMOVED (moved to gluetun service) |
| `depends_on` | (unset) | `{gluetun: {condition: service_healthy}}` |
| `volumes` | unchanged | unchanged — `/mnt/nas/torrents` mount preserved (FR-007, Edge Case) |
| `environment` | unchanged | unchanged |

### Validation

- `docker inspect deluge | jq '.[0].HostConfig.NetworkMode'` MUST return `container:<gluetun-id>` (research R5 T5; FR-002).
- LAN reachability preserved (FR-008): Sonarr/Radarr/Prowlarr on the same Compose project reach Deluge via `gluetun:8112` and `gluetun:58846` (not `deluge:...`).

---

## E3. Port Forwarding Hook Script

**Lives in**: `infrastructure/torrentbox/gluetun-port-hook.sh` (repo) bind-mounted into gluetun at `/gluetun-scripts/`.

### Behavior

```bash
#!/usr/bin/env bash
# Arg: $1 = PIA-assigned forwarded port
set -euo pipefail
PORT="$1"
docker exec deluge deluge-console -c /config "config --set listen_ports ($PORT,$PORT)"
docker exec deluge deluge-console -c /config "config --set random_port False"
```

### Invocation

- Triggered by gluetun via `VPN_PORT_FORWARDING_UP_COMMAND="/gluetun-scripts/gluetun-port-hook.sh {{PORT}}"`.
- Fires on initial tunnel-up AND on every PIA port rotation (every ~60 days).
- Requires the Docker socket to be reachable from gluetun — TBD Phase 2 decision (host-side script vs socket mount). Default: **host-side wrapper** that gluetun invokes via a host-shared path; avoids mounting `/var/run/docker.sock` into gluetun.

### Validation

- Script is `+x` permissions, shebang is a real `#!/usr/bin/env bash` (explicit protection against the 014 incident class).
- Hook propagates within 60 seconds of a port-rotation event (FR-017, SC-007).

---

## E4. Deluge External-IP Health Check (NEW in Advisor)

**Lives in**: `advisor/backend/app/services/health_checks/deluge_external_ip.py`.
**Writes to**: existing `HealthCheckResult` table (Phase 4.5 schema, no migration).

### Probe mechanism

- Periodically (on the Advisor's existing check schedule) obtain Deluge's external IP.
- Candidate mechanisms (Phase 2 decision):
  - (a) Call a tiny HTTP endpoint on the Torrentbox host that runs `docker exec deluge curl -s --max-time 5 ifconfig.me` and returns the result.
  - (b) Use docker-py to exec the command directly from HOLYGRAIL against the remote Docker API (requires Docker socket exposure on Torrentbox over TLS — meaningful new exposure, probably rejected).
  - (c) SSH + docker exec — reuses the existing `john@torrentbox` SSH setup. Simplest in the short term.
- **Default pick**: (c), SSH-based. Documented trade-off: rotational SSH host keys could break the probe; mitigated by pinning known_hosts on HOLYGRAIL.

### Fields written into `HealthCheckResult`

| Field | Value |
|-------|-------|
| `service_id` | A new service registration: name=`deluge-vpn`, host_label=`torrentbox` |
| `checked_at` | Probe timestamp (UTC) |
| `status` | `green` if observed IP NOT in denylist; `red` if observed IP ∈ denylist; `yellow` if probe could not reach Deluge (soft warning per FR-014) |
| `details` | JSON blob: `{"observed_ip": "<ip>", "denylist_matched": bool, "probe_error": "<str or null>"}` |

### Denylist source

Configured via rows in the existing `AlertThreshold` table using the **rule-prefixed key convention** (matches `device_offline_minutes` / `service_down_minutes` in existing rules):

- `rule_id = "vpn_leak"`, `key = "vpn_leak_denylist_ips"`, `value = ["67.176.27.48"]` (home WAN IP at feature time). Minimum required entry per FR-010.
- `rule_id = "vpn_leak"`, `key = "vpn_leak_escalation_threshold"`, `value = 3` (per Clarification Q2 + FR-012).

Operator MAY extend the denylist via the Advisor settings UI; MUST NOT fall below the home-WAN-IP baseline.

---

## E5. VPN Leak Rule (NEW in Advisor)

**Lives in**: `advisor/backend/app/services/rules/vpn_leak.py`.
**Registered in**: `advisor/backend/app/services/rules/__init__.py`.

### Fields (Rule subclass)

| Field | Value |
|-------|-------|
| `id` | `vpn_leak` |
| `name` | `Deluge VPN leak` |
| `severity` | `critical` |
| `sustained_window` | `timedelta(0)` (each evaluation is independent; escalation counted separately — see below) |

### Evaluate logic (pseudocode)

```python
async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
    denylist = set(ctx.thresholds.get("vpn_leak_denylist_ips", []))
    # Find the deluge-vpn service's latest HealthCheckResult.
    latest = ctx.health_results.get(deluge_vpn_service_id)
    if latest is None:
        return []  # no probe yet — nothing to evaluate
    if latest.status == "yellow":
        # FR-014: soft warning, NOT a leak alert. Emitted separately if desired.
        return []
    observed_ip = latest.details.get("observed_ip")
    if latest.status == "red" and observed_ip in denylist:
        # Confirmed leak. Exact string equality via set membership — NOT substring match.
        return [RuleResult(
            target_type="service",
            target_id=deluge_vpn_service_id,
            message=f"Deluge egressing on {observed_ip} (matches denylist)",
        )]
    return []
```

**Match-logic note**: use **set membership** (`observed_ip in denylist`), not substring (`any(ip in observed_ip for ip in denylist)`). Substring matching would incorrectly fire for partial-prefix collisions (e.g., denylist `"67.176.27.4"` matching observed `"67.176.27.48"`). Exact string equality is the correct semantics for IP address comparisons.

### Escalation + remediation (extension to current rule engine)

Current Advisor rules only emit alerts. For FR-012 we add a narrow extension:

| Field | Description |
|-------|-------------|
| `escalation_threshold` | Count of consecutive leak alerts before `on_escalate` fires (default: 3 per Clarification Q2) |
| `on_escalate` action | Call a new `remediation.stop_container(host="torrentbox", container="deluge")` helper; emits a distinct `Alert` with `rule_id="vpn_leak:remediation"` |
| `remediation_enabled` | Boolean threshold row default `true` for this rule, false for all others (no backward-compat concern) |

The `remediation` helper uses SSH (same mechanism as E4 option c) to run `docker stop deluge` on Torrentbox. Phase 2 will decide whether to generalise this (likely not — keep narrow to this rule until a second use case appears).

**Escalation counter persistence — explicit tradeoff**: the consecutive-fire count is held **in-memory** within the rule engine process. If the Advisor restarts (deploy, crash, power cycle) mid-leak, the counter resets to zero and Deluge could dodge auto-stop as long as restarts outpace three leak ticks. Accepted because: (a) Advisor restarts are operator-initiated events, measured in minutes, with bounded exposure (worst case a few extra leak ticks); (b) persisting the counter adds a table or column that carries no value outside this one rule; (c) the alerts themselves are persisted in the `Alert` table and visible regardless — the operator will see leak alerts across a restart, just not auto-stop unless three consecutive ticks occur within one process lifetime. If this ever becomes a real incident class, reconsider via a small column on the latest `Alert` row or a dedicated `RuleEscalationState` table.

### Test file

`advisor/backend/tests/test_rule_vpn_leak.py` covers:

- Empty `health_results` → no alerts.
- Latest result green → no alerts.
- Latest result yellow → no alerts (soft warning semantics).
- Latest result red with denylist-matching IP → one `RuleResult` critical.
- Three consecutive red results → escalation path invoked (mock the SSH helper).
- Red result with non-denylist IP → no alert (catches misconfiguration where VPN exit rotates but is still VPN).

---

## E7. VPN Status Summary (API response shape)

**Lives in**: `advisor/backend/app/routers/vpn.py` (new router), exposed at `GET /api/vpn-status`.
**Consumed by**: `VpnStatusCard.tsx` (dashboard card) and `NavStatusPill.tsx` (top-nav pill).

### Derivation

Summarizes three existing data sources into one of five states per FR-013:

- Latest `HealthCheckResult` for the `deluge-vpn` service (status + details.observed_ip)
- Any unresolved `Alert` rows with `rule_id="vpn_leak"` or `rule_id="vpn_leak:remediation"`
- Heartbeat age: `now - latest_health_check.checked_at`; if > 2 × rule-engine interval, state is **WATCHDOG DOWN**

### State precedence (ordered, first match wins)

1. **AUTO-STOPPED** — if an active `Alert` with `rule_id="vpn_leak:remediation"` exists (highest urgency)
2. **LEAK DETECTED** — if an active (non-acknowledged) `Alert` with `rule_id="vpn_leak"` exists
3. **WATCHDOG DOWN** — if heartbeat age > 2 × rule-engine interval
4. **PROBE UNREACHABLE** — if latest `HealthCheckResult.status == "yellow"` (soft warning, FR-014)
5. **OK** — if latest `HealthCheckResult.status == "green"` and observed_ip is in an accepted range
6. (fallback) **UNKNOWN** — no prior `HealthCheckResult` exists yet (first deploy, before first probe)

### Response shape

```json
{
  "state": "OK | LEAK_DETECTED | PROBE_UNREACHABLE | WATCHDOG_DOWN | AUTO_STOPPED | UNKNOWN",
  "observed_ip": "181.41.206.98",
  "last_probe_at": "2026-04-14T10:15:03Z",
  "last_probe_age_seconds": 127,
  "active_alert_id": null,
  "active_remediation_alert_id": null,
  "message": "Tunnel up · exit 181.41.206.98 · probed 2m ago"
}
```

- `observed_ip` may be null in WATCHDOG_DOWN or UNKNOWN states.
- `active_alert_id` and `active_remediation_alert_id` are the `Alert.id`s the UI links to for the "View alert" action.
- `message` is a pre-rendered human-readable summary suitable for the dashboard card and tooltip.

### Validation rules (from Requirements)

- Response reflects state within one check interval of any change (FR-013c).
- Five distinguishable states render to distinct colors in the card (FR-013 table).
- Endpoint is read-only; no state mutation.

### Frontend mapping

| API state | Card color / layout | Nav pill |
|-----------|---------------------|----------|
| OK | green compact card, shows message | `VPN · OK` green |
| LEAK_DETECTED | red persistent banner, "View alert" button | `VPN · ⚠ LEAK` red |
| PROBE_UNREACHABLE | yellow card, "Probe cannot reach Deluge" | `VPN · ? ` yellow |
| WATCHDOG_DOWN | gray card, "No heartbeat for N min" | `VPN · ∅ ` gray |
| AUTO_STOPPED | red card with action badge, "Deluge stopped by auto-remediation" | `VPN · ⛔ STOPPED` red |
| UNKNOWN | gray card, "Awaiting first probe" | `VPN · …` gray |

---

## E6. Legacy Archive (Pi-only, not in repo)

**Location on Pi after US-4**: `/etc/openvpn/legacy-014/`
**Contents**: `pia.conf`, `vpn-up.sh`, `vpn-down.sh`, `pia-credentials.txt` (mv'd from `/etc/openvpn/`).

### Validation

- `systemctl is-enabled openvpn@pia` returns `disabled` (FR-019).
- `sudo iptables -L OUTPUT -n --line-numbers` returns default-ACCEPT policy with zero explicit rules (FR-021, SC-008).
- `/etc/openvpn/` contains no references to the archived files outside the `legacy-014/` subdirectory (FR-020).

---

## Relationships

```text
(Compose E1 gluetun) ——provides netns—→ (Compose E2 deluge)
(Compose E1 gluetun) ——invokes on PF——→ (Hook E3)
(Hook E3) ——docker exec—→ (Deluge listen_ports config)

(Advisor Health Check E4) ——writes—→ HealthCheckResult (existing table)
(Advisor Rule E5) ——reads—→ HealthCheckResult + AlertThreshold (existing tables)
(Advisor Rule E5) ——writes—→ Alert (existing table)
(Advisor Rule E5 on_escalate) ——SSH→ (Torrentbox Docker: stop deluge)

(Legacy Archive E6) ——archived once—→ /etc/openvpn/legacy-014/
```

No new tables, no state machines beyond the existing Advisor Alert lifecycle (active → acknowledged → resolved). The escalation counter is in-memory within the rule engine's evaluation context.
