# Contracts: VPN Sidecar Migration & Kill-Switch Hardening

**Feature**: 015-vpn-sidecar
**Date**: 2026-04-14

This feature produces **one new internal contract** (the Advisor rule's output shape, following the existing `RuleResult` pattern) and consumes several existing external interfaces. No new public REST endpoints are introduced. The Advisor's `/alerts` REST API (documented in Phase 4.5 contracts) is consumed unchanged.

---

## External interfaces consumed

### Gluetun control server

Base URL: `http://localhost:8000` (inside gluetun's netns; only accessed from within the container or from Deluge, which shares the netns).
Documentation: [gluetun-wiki/setup/advanced/control-server](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md)

| Endpoint | Used for | Mapped requirement |
|----------|----------|--------------------|
| `GET /v1/openvpn/portforwarded` | Forward-compatible source of the current PIA-assigned port | FR-015, research R3 |

The hook script uses the `VPN_PORT_FORWARDING_UP_COMMAND` template substitution instead of polling this endpoint, but the endpoint remains the long-term source of truth if we ever move away from the hook.

### PIA API (indirectly)

Consumed by gluetun itself; no direct contract from this feature. PIA's port-forwarding API rotates tokens ~60 days; gluetun handles the refresh transparently as long as `/gluetun` is persisted (research R3).

### Deluge RPC / Web API

Host: `gluetun:58846` (daemon RPC) / `gluetun:8112` (web UI) — note "gluetun" because Deluge shares that netns.

| Mechanism | Used for | Mapped requirement |
|-----------|----------|--------------------|
| `deluge-console config --set listen_ports (P,P)` via `docker exec` | Apply PIA-assigned port without restart | FR-016, research R3 |
| `deluge-console config --set random_port False` | Bootstrap; run once during initial migration | FR-016 |

No Deluge REST schema changes — we use the console CLI inside the container.

### Docker Engine API (remote, via SSH)

Used by the Advisor on HOLYGRAIL to execute the auto-stop remediation on Torrentbox.

| Command | Purpose | Mapped requirement |
|---------|---------|--------------------|
| `ssh torrentbox docker stop deluge` | Auto-remediation on 3-consecutive-leak escalation | FR-012, Clarification Q2 |
| `ssh torrentbox docker exec deluge curl -s --max-time 5 ifconfig.me` | External-IP probe (default probe mechanism — research R7 option c) | FR-010, FR-014 |

Existing SSH config on HOLYGRAIL already has passwordless access to `torrentbox` (per `scripts/ssh-config`). No new credentials needed.

### Advisor internal interfaces (consumed, not modified)

- `HealthCheckResult` model (existing; Phase 4.5). Our new health-check source writes rows; our new rule reads them.
- `Alert` model (existing; Phase 4.5). Our rule produces alerts via the existing `RuleResult` → `Alert` pipeline.
- `AlertThreshold` model (existing; Phase 4.5). Hosts the `vpn_leak_denylist_ips` config and the `vpn_leak_escalation_threshold` override.
- `Rule` abstract base (`advisor/backend/app/services/rules/base.py`). `VpnLeakRule` subclasses this unchanged.

---

## Contracts produced by this feature

### `RuleResult` payload for `vpn_leak`

```python
RuleResult(
    target_type="service",
    target_id=<deluge_vpn_service.id>,
    message=f"Deluge egressing on {observed_ip} (matches denylist)",
)
```

Fields follow the existing `RuleResult` dataclass in `advisor/backend/app/services/rules/base.py`. No new schema.

### `GET /api/vpn-status` (new endpoint)

**Purpose**: Summarize current VPN tunnel health into one of six states for prominent dashboard surfacing (FR-013).

**Location**: `advisor/backend/app/routers/vpn.py` (new router, registered in `app/main.py`).

**Auth**: Same as other Advisor read endpoints — LAN-internal, no auth (the whole Advisor is LAN-only).

**Request**: No parameters.

**Response 200**:

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

Full field semantics + state precedence rules: see data-model.md E7.

**Error responses**: none currently defined — endpoint is read-only over existing DB state. If the DB is unreachable, the standard FastAPI 500 applies.

**Consumers**:

- `advisor/frontend/src/services/vpn.ts` — typed client wrapper.
- `advisor/frontend/src/components/VpnStatusCard.tsx` — dashboard card.
- `advisor/frontend/src/components/NavStatusPill.tsx` — top-nav pill.

**Mapped requirement**: FR-013, plus US-2 acceptance scenarios 5, 6, 7.

### `RuleResult` payload for `vpn_leak:remediation`

Emitted once per escalation event (not per leak check):

```python
RuleResult(
    target_type="service",
    target_id=<deluge_vpn_service.id>,
    message=f"Auto-stopped Deluge after 3 consecutive leak detections (latest IP: {observed_ip})",
)
```

Mapped requirement: FR-012.

### Torrentbox Compose file shape

New file at `infrastructure/torrentbox/docker-compose.yml`. The **observable contract** from the repo's perspective:

- `services` includes at minimum: `gluetun`, `deluge`, `sonarr`, `radarr`, `prowlarr`, `flaresolverr`, `lidarr`, `lazylibrarian` (same set as current Pi state).
- `deluge.network_mode` = `"service:gluetun"`.
- `deluge` has no `ports` block (moved to gluetun).
- `deluge` has no `networks` block (research R5 T5 — bypass trap).
- `gluetun` publishes Deluge's ports (`8112`, `58846`) AND its own control-server port (`8000`, loopback only ideally).

See `data-model.md` E1 and E2 for full field shapes.

### Shell hook script contract

`infrastructure/torrentbox/gluetun-port-hook.sh`:

- **Input**: a single positional argument `$1` (integer port).
- **Behavior**: propagates the port to Deluge's `listen_ports` and sets `random_port=False`.
- **Exit code**: 0 on success; non-zero on propagation failure (propagation failure does NOT tear down gluetun — the hook is fire-and-log).

Mapped requirement: FR-016.

---

## Versioning stance

- gluetun tag is pinned (see research R6) and upgraded via explicit PR review. Upstream breaking-change discipline is enforced by reading the gluetun CHANGELOG before each bump.
- Advisor internal contracts (`Rule`, `RuleResult`, `HealthCheckResult`) are versioned by the Advisor repo's own conventions — this feature follows, doesn't define.
- Deluge `deluge-console` CLI is stable across linuxserver image versions but pinned tags for `linuxserver/deluge` would reduce risk. Image pinning is a broader hygiene concern already noted in the 014 feature commit (`:latest` landmine) and may be addressed here as drive-by hygiene.

---

## Security considerations

- PIA credentials live only in `/home/john/docker/.env` on Torrentbox. Never committed. Never logged (gluetun `LOG_LEVEL=info`).
- SSH from HOLYGRAIL to Torrentbox is already trusted LAN-only. The probe + remediation use that existing trust relationship. No new credential surfaces.
- Gluetun control server (`:8000`) is bound to loopback inside the sidecar netns by default; verify this in the Compose — it must not be exposed on a host port.
- `FIREWALL_OUTBOUND_SUBNETS` is scoped to `192.168.10.0/24` only. Widening this at runtime silently defeats the kill-switch (research R5); the Compose definition is the authoritative gate.
