# Implementation Plan: VPN Sidecar Migration & Kill-Switch Hardening

**Branch**: `015-vpn-sidecar` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/Users/jd/Code/camelot/specs/015-vpn-sidecar/spec.md`

## Summary

Replace host-level `openvpn@pia.service` on Torrentbox with a **gluetun sidecar container** using native PIA WireGuard provider mode. Migrate Deluge to `network_mode: service:gluetun` so its network namespace is fully owned by the sidecar; gluetun's built-in default-deny iptables firewall becomes the kill-switch (no container escape when tunnel drops). Automate PIA port forwarding via gluetun's `VPN_PORT_FORWARDING_UP_COMMAND` hook, pushing the assigned port into Deluge's live `listen_ports` via `deluge-console`. Implement a **tunnel-health watchdog as a new Advisor rule** (`vpn_leak`) running on HOLYGRAIL, evaluating Deluge's external IP against a denylist (per Clarification Q1, minimum entry = home WAN IP) with 3-strike auto-remediation that stops the Deluge container (per Clarification Q2). Move the Torrentbox Compose file under repo-committed `infrastructure/torrentbox/` (currently live-edited on the Pi) so the box becomes repo-reproducible per FR-023. After 7 stable days, decommission and archive the legacy `openvpn@pia` stack.

## Technical Context

**Language/Version**: Python 3.12 (Advisor backend — new rule + new health check source). Bash for the `VPN_PORT_FORWARDING_UP_COMMAND` shim script and the quickstart validation. No new long-running service code beyond the Advisor rule.
**Primary Dependencies**: `qmcgaw/gluetun` (pinned tag, e.g. `v3.40.0`) on Torrentbox; existing `linuxserver/deluge`. Advisor: existing FastAPI 0.115 + SQLAlchemy 2.0 async. No new Python packages added. The external-IP probe uses `asyncio.create_subprocess_exec` to invoke `ssh torrentbox "docker exec deluge curl …"` — reuses the existing HOLYGRAIL→Torrentbox SSH trust relationship (research R7 option c + contracts/README.md). No `httpx`, no direct Docker-API call, no new credential surface.
**Storage**: No new DB tables. Existing `HealthCheckResult` table captures the Deluge external-IP probe result (source of truth for the new rule). Existing `Alert` + `AlertThreshold` + `NotificationSink` tables (from Phase 4.5) handle alert lifecycle, thresholds, and delivery. Gluetun persists its state at a bind-mounted `/home/john/docker/gluetun/` directory on the Pi for 60-day PIA PF token continuity (critical — see research R3).
**Testing**: Manual behavioral validation per `quickstart.md` (kill-switch tests 1–5 from research R5). New pytest test for the `vpn_leak` Advisor rule in `advisor/backend/tests/test_rule_vpn_leak.py`, following the pattern of `test_rule_engine.py` (rule evaluated with synthetic `HealthCheckResult` + expected `RuleResult`). No pytest added on Torrentbox — verification is observational.
**Target Platform**: Torrentbox Pi 5 (192.168.10.141, Debian Trixie, arm64) for gluetun + deluge. HOLYGRAIL (192.168.10.129) for the Advisor rule. LAN only.
**Project Type**: Mixed — infrastructure refactor (Torrentbox Compose) + small backend feature (new Advisor rule, probe source, status-summary endpoint) + small frontend feature (prominent VPN status card + top-nav pill per FR-013).
**Performance Goals**: Per SC-001–SC-010 in spec. Watchdog check interval ≤ 15 min (FR-010). Kill-switch verification: Deluge external-IP probe fails within 10s of sidecar stop (SC-002). Cutover disruption: target minutes, not hours (Assumptions).
**Constraints**: (a) No credentials in repo (FR-006 — gluetun env vars sourced from `.env` on the Pi, gitignored). (b) Preserve *arr → Deluge → NAS → Plex pipeline (FR-007). (c) LAN reachability to Deluge UI preserved (FR-008). (d) In-flight downloads may be lost at cutover (acceptable per Assumptions). (e) Rollback to legacy in <60 min from first 7 days (FR-026, SC-009).
**Scale/Scope**: Single Torrentbox, 1 new container (gluetun), 1 modified container (deluge networking + port publication moved to gluetun). Advisor gets 1 new rule + 1 new health-check probe source. `infrastructure/torrentbox/` directory introduced (net-new in repo).

### Decisions deferred to planning, now resolved (see research.md)

- **Sidecar image**: **gluetun** (`qmcgaw/gluetun`), pinned to a specific tag. See research R1.
- **VPN protocol**: **WireGuard via gluetun's native PIA provider** (`VPN_SERVICE_PROVIDER=private internet access`, not `custom`). OpenVPN is fallback only if WG PF misbehaves in practice. See research R2.
- **Watchdog host**: **HOLYGRAIL** via a new Advisor rule, not Torrentbox cron. Rationale in research R7 (integration with existing alert pipeline, external vantage point catches "Torrentbox down" as well as "Deluge leaking").
- **Port-forwarding propagation**: `VPN_PORT_FORWARDING_UP_COMMAND` with `{{PORT}}` template calling a bash script that runs `deluge-console config --set listen_ports (P,P)` via `docker exec`. No Deluge restart needed. See research R3.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**I. Local-First** — Pass. Everything remains on the LAN. gluetun's outbound traffic is PIA, falling under the constitution's explicit "torrent traffic" allowance. No cloud APIs. Credentials stay on the Pi in a gitignored `.env`.

**II. Simplicity & Pragmatism** — Pass. One new container (gluetun), one new Advisor rule, one new bash hook script. No new abstractions; the feature uses gluetun's built-in firewall + port-forwarding + healthcheck rather than re-implementing any of them. Advisor rule follows the existing `Rule` class pattern verbatim.

**III. Containerized Everything** — Pass. This principle is arguably strengthened by the feature: we replace a host-level systemd service (`openvpn@pia`) with a containerized equivalent. All VPN state moves into `/home/john/docker/gluetun/`. Compose file moves into `infrastructure/torrentbox/` in the repo, bringing the Pi under version control per the "configuration lives in the repo" clause.

**IV. Test-After (Not Test-First)** — Pass. Validation is manual (quickstart) + an after-the-fact pytest for the new rule. No TDD pressure. The kill-switch verification matrix in research R5 is the de-facto behavioral test plan.

**V. Observability** — Pass. This feature is **primarily** an observability feature — the watchdog exists specifically to make silent failures loud. FR-010/011/012/013 define alert, remediation, and heartbeat surfaces. The Advisor rule engine is the observability layer. Degrades gracefully if Advisor is offline (per spec Assumptions).

**Result**: No violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/015-vpn-sidecar/
├── plan.md              # This file
├── research.md          # Phase 0: gluetun selection, WG vs OpenVPN, PF propagation, Compose ordering, kill-switch verification, watchdog host
├── data-model.md        # Phase 1: gluetun config, Deluge network-mode change, Alert flow, vpn_leak rule inputs
├── quickstart.md        # Phase 1: Behavioral validation (kill-switch tests 1–5, PF end-to-end, watchdog fire + auto-stop)
├── contracts/
│   └── README.md        # Phase 1: External interfaces touched (gluetun control server, Deluge Web API, Advisor Alert/HealthCheckResult schemas)
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # /speckit.tasks output (not produced here)
```

### Source Code (repository root)

```text
infrastructure/
└── torrentbox/                         # NEW directory (CLAUDE.md notes this as "future: Docker Compose from Pi" — this feature creates it)
    ├── docker-compose.yml              # NEW: gluetun + deluge + sonarr + radarr + prowlarr + flaresolverr + lidarr + lazylibrarian, with gluetun as the VPN sidecar for deluge only
    ├── .env.example                    # NEW: template for PIA credentials (real .env lives on Pi, gitignored)
    ├── gluetun-port-hook.sh            # NEW: VPN_PORT_FORWARDING_UP_COMMAND target — pushes {{PORT}} into deluge-console
    └── README.md                       # NEW: deploy procedure (rsync to Pi + docker compose up)

advisor/backend/app/services/
├── rules/
│   ├── vpn_leak.py                     # NEW: Rule firing when Deluge external IP ∈ denylist (≥ home WAN IP)
│   └── __init__.py                     # MODIFIED: register VpnLeakRule
└── health_checks/
    └── deluge_external_ip.py           # NEW: health-check source that probes Deluge's external IP via its Web API and writes to HealthCheckResult

advisor/backend/app/routers/
└── vpn.py                              # NEW: GET /api/vpn-status endpoint — summarizes the 5 states (OK / LEAK / PROBE UNREACHABLE / WATCHDOG DOWN / AUTO-STOPPED) from HealthCheckResult + Alert + heartbeat age

advisor/backend/tests/
├── test_rule_vpn_leak.py               # NEW: pytest for the new rule (synthetic HealthCheckResult inputs → expected RuleResult)
└── test_vpn_status_endpoint.py         # NEW: pytest for the 5-state summarizer (synthetic DB state → expected response shape)

advisor/frontend/src/components/
├── VpnStatusCard.tsx                   # NEW: prominent dashboard card, top of main view
└── NavStatusPill.tsx                   # NEW: persistent top-nav pill on every page

advisor/frontend/src/services/
└── vpn.ts                              # NEW: typed client for GET /api/vpn-status

advisor/frontend/src/pages/Dashboard.tsx  # MODIFIED: inject VpnStatusCard at top
advisor/frontend/src/components/Navigation.tsx  # MODIFIED (exact filename TBD at implementation): inject NavStatusPill

docs/
├── INFRASTRUCTURE.md                   # MODIFIED: Torrentbox section rewritten for sidecar topology; architectural-gaps list updated (gaps 1+4 closed upon US-4); legacy VPN description moved to historical footnote
├── F5.3-vpn-sidecar-migration.md       # ALREADY EXISTS (master) — no change
└── (archived on Pi, not in repo) /etc/openvpn/legacy-014/{pia.conf, vpn-up.sh, vpn-down.sh, pia-credentials.txt}

# No changes under advisor/frontend/, advisor/backend/app/models/, or advisor/backend/migrations/ — reusing existing schema.
```

**Structure Decision**: **Infrastructure-as-code introduction + small backend feature.** The feature has three distinct surfaces: (1) a new repo-committed Compose file for the Torrentbox (first occupant of `infrastructure/torrentbox/`); (2) a new Advisor Rule + health-check source under the existing backend pattern; (3) a small bash hook co-located with the Compose file. No new modules, no new migrations, no frontend work. The `infrastructure/torrentbox/` directory materializes for the first time here — CLAUDE.md already forecasted this as "future." Deploy model: `rsync infrastructure/torrentbox/ torrentbox:/home/john/docker/` + `docker compose up -d` (documented in the new README).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations to track.
