---
description: "Task list for feature 015-vpn-sidecar"
---

# Tasks: VPN Sidecar Migration & Kill-Switch Hardening

**Input**: Design documents from `/Users/jd/Code/camelot/specs/015-vpn-sidecar/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Per Constitution IV (Test-After), a pytest for the new Advisor rule (`test_rule_vpn_leak.py`) is written **after** the rule implementation, not before. No other test files are authored — the kill-switch verification matrix in `quickstart.md` (T1–T5) is the behavioral validation harness for US-1, and manual steps cover US-2 through US-4.

**Organization**: Tasks are grouped by user story (P1 → P2 → P3 → P4) so each story can be implemented, demoed, and rolled back independently. US-4 is gated on 7 days of US-1+US-2 stability.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or different surfaces, no dependency on an incomplete task)
- **[Story]**: US1 (sidecar + kill-switch), US2 (watchdog), US3 (port forwarding), US4 (legacy decommission)

## Path Conventions

Two surfaces:

1. **Repo paths (Mac workstation)** — source of truth for Compose + Advisor:
   - [infrastructure/torrentbox/](../../infrastructure/torrentbox/) — NEW directory; Compose file + .env.example + hook script + README
   - [advisor/backend/app/services/rules/](../../advisor/backend/app/services/rules/) — new `vpn_leak.py`
   - [advisor/backend/app/services/health_checks/](../../advisor/backend/app/services/health_checks/) — new `deluge_external_ip.py`
   - [advisor/backend/tests/](../../advisor/backend/tests/) — new `test_rule_vpn_leak.py`
   - [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) — modified (sidecar topology)

2. **Live deployment paths (Torrentbox + HOLYGRAIL)** — not in repo:
   - `/home/john/docker/` — Torrentbox Compose runtime (synced from `infrastructure/torrentbox/`)
   - `/home/john/docker/gluetun/` — gluetun state (persistent, NOT in repo)
   - `/home/john/docker/.env` — PIA credentials (on Pi only, gitignored)
   - `/etc/openvpn/legacy-014/` — archive location after US-4
   - `/home/john/advisor/` on HOLYGRAIL — via existing `scripts/deploy-advisor.sh`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Pre-flight checks, capture pre-migration state, prepare rollback blob.

- [ ] T001 Verify the post-014 healthy state: `ssh torrentbox "sudo systemctl is-active openvpn@pia"` returns `active`, and `ssh torrentbox "docker exec deluge curl -s --max-time 5 ifconfig.me"` returns a PIA IP (**NOT** `67.176.27.48`). If either check fails, STOP — 014's fix may have regressed and needs diagnosis before this feature continues.
- [ ] T002 Record the **current home WAN IP** for the watchdog denylist. Run `curl -s ifconfig.me` from the Mac (or any home LAN device). Write the value to a scratch note for use in T028 and T032. This is the minimum required denylist entry per FR-010.
- [ ] T003 [P] Capture the **current PIA credentials** from the Pi so they can be reused in the sidecar's `.env`: `ssh torrentbox "sudo cat /etc/openvpn/pia-credentials.txt"`. Store the two lines (username, password) in your password manager. Do NOT write them into any repo file or scratch note that could leak.
- [ ] T004 [P] Snapshot current Torrentbox deployment directory for rollback: `ssh torrentbox "sudo cp -a /home/john/docker /home/john/docker.bak-015-$(date +%Y%m%d) && ls -ld /home/john/docker.bak-015-*"`. This is the FR-026 rollback blob.
- [ ] T005 [P] Create `infrastructure/torrentbox/` directory in the repo (currently does not exist — CLAUDE.md marks it as "future placeholder"). This is the home for all new Compose + hook artifacts.

**Checkpoint**: Pre-flight green, baseline IP recorded, credentials captured locally, rollback blob in place, repo directory ready.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Verify cross-host plumbing that US-1 and US-2 both depend on: Advisor can reach Torrentbox for probing + remediation, Advisor rule-engine schedule meets the spec.

**CRITICAL**: US-2 cannot ship without T007 (the probe path) and T008 (the remediation path). Without Phase 2 checks, US-2 might be implemented but silently non-functional.

- [ ] T006 Verify HOLYGRAIL's existing SSH access to Torrentbox: `ssh holygrail "ssh torrentbox 'echo SSH_OK && docker ps --format {{.Names}} | head -3'"`. Expected: `SSH_OK` plus the container list. If this fails, HOLYGRAIL's SSH-to-Torrentbox needs fixing first (ssh-config + host-key pinning). This plumbing is the basis of the watchdog probe and auto-remediation.
- [ ] T007 [P] Verify the Advisor's rule engine schedule interval — inspect [advisor/backend/app/services/rule_engine.py](../../advisor/backend/app/services/rule_engine.py) for the scheduling cadence. If the cadence is > 15 minutes, note it for T024 (the watchdog's own scheduling check) and raise the question before proceeding. Per FR-010 the watchdog probe must run at least every 15 min.
- [ ] T008 [P] Check `HealthCheckResult` schema fields — inspect [advisor/backend/app/models/health_check_result.py](../../advisor/backend/app/models/health_check_result.py). Confirm the `details` column accepts a JSON blob (needed for `{"observed_ip": ..., "denylist_matched": ...}` per data-model.md E4). If it doesn't, note as a schema question for T023.
- [ ] T009 [P] Confirm `docker-py` is already a dependency of the Advisor backend — grep [advisor/backend/requirements.txt](../../advisor/backend/requirements.txt). If not present, note for T025 — though the SSH-based probe path (research R7 option c) does not strictly require docker-py, only `subprocess`.

**Checkpoint**: All cross-host and cross-schema plumbing verified. Any blockers surfaced before implementation burns time.

---

## Phase 3: User Story 1 - Sidecar VPN Container with Default-Deny Kill-Switch (Priority: P1) 🎯 MVP

**Goal**: Deluge runs inside gluetun's netns. The kill-switch is proven by the full 5-test matrix in quickstart. The *arr → Deluge → NAS → Plex pipeline still works end-to-end.

**Independent Test**: Complete quickstart.md US-1 validation (Steps 1.1 through 1.5). This ships the security win even without US-2/US-3/US-4.

**Scope maps to**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-023, FR-024, FR-025 · SC-001, SC-002, SC-003, SC-010.

### Implementation for User Story 1

- [X] T010 [P] [US1] Author [infrastructure/torrentbox/docker-compose.yml](../../infrastructure/torrentbox/docker-compose.yml) — full replacement of the current Pi Compose. Declare services: `gluetun` (pinned `qmcgaw/gluetun:v3.40.0` or latest stable; `cap_add: [NET_ADMIN]`; `devices: [/dev/net/tun:/dev/net/tun]`; `volumes: [/home/john/docker/gluetun:/gluetun, /home/john/docker/torrentbox/gluetun-port-hook.sh:/gluetun-scripts/gluetun-port-hook.sh:ro]`; `env_file: [/home/john/docker/.env]`; `ports: [8112:8112, 58846:58846, 8989:8989? — see T012]`; custom healthcheck hitting `https://ipinfo.io/ip`), `deluge` (unchanged volumes + env; **add** `network_mode: "service:gluetun"`; **remove** `ports:` block; **omit** `networks:`; `depends_on: {gluetun: {condition: service_healthy}}`). Preserve all other *arr services (sonarr/radarr/prowlarr/flaresolverr/lidarr/lazylibrarian) unchanged. See data-model.md E1 + E2 for exact field values.
- [X] T011 [P] [US1] Author [infrastructure/torrentbox/.env.example](../../infrastructure/torrentbox/.env.example) — template showing `OPENVPN_USER`, `OPENVPN_PASSWORD`, `VPN_SERVICE_PROVIDER=private internet access`, `VPN_TYPE=wireguard`, `SERVER_REGIONS=US Denver`, `VPN_PORT_FORWARDING=on`, `VPN_PORT_FORWARDING_PROVIDER=private internet access`, `VPN_PORT_FORWARDING_UP_COMMAND=/gluetun-scripts/gluetun-port-hook.sh {{PORT}}`, `FIREWALL=on`, `FIREWALL_OUTBOUND_SUBNETS=192.168.10.0/24`, `LOG_LEVEL=info`, `HEALTH_TARGET_ADDRESS=1.1.1.1:443`. Values for credentials are placeholders (`<redacted>`). This file IS committed.
- [X] T012 [US1] Decide on port-publication strategy for the *arr services: if Sonarr/Radarr/Prowlarr etc. stay on the default bridge (not behind gluetun), their ports publish normally on their own service declarations. The gluetun service publishes ONLY Deluge's ports (`8112`, `58846`). Confirm this in T010 and fix if the initial draft put all ports on gluetun. Depends on T010.
- [X] T013 [P] [US1] Author [infrastructure/torrentbox/gluetun-port-hook.sh](../../infrastructure/torrentbox/gluetun-port-hook.sh) — per data-model.md E3. **Write the shebang via a real editor**, never via `echo` or heredoc (the 014 incident class). Start with `#!/usr/bin/env bash`, then `set -euo pipefail`, then the port-propagation logic. Make the file executable (`chmod +x`). Add a guard: if `$1` is empty or non-numeric, log and exit 1 (do NOT tear down gluetun).
- [X] T014 [P] [US1] Verify the T013 shebang is a real `#!` on disk: `head -c 3 infrastructure/torrentbox/gluetun-port-hook.sh | od -c` — expected first three characters are `# !` (in od-c notation, so `# !` literally == `0x23 0x21 0x2f` = `#!/`). If you see a `\` in the second position, the file was written with the 014 bug and must be rewritten. This is belt-and-suspenders, but cheap and directly addresses lessons learned.
- [X] T015 [P] [US1] Author [infrastructure/torrentbox/README.md](../../infrastructure/torrentbox/README.md) — deploy procedure: (a) create `.env` on the Pi from `.env.example`, (b) rsync the directory to the Pi, (c) `docker compose up -d`, (d) validate via quickstart.md US-1. Include pinning discipline + rollback procedure pointers.
- [ ] T016 [US1] Rsync repo artifacts to the Pi into a parallel path (not yet overwriting live): `rsync -av --exclude='.env' infrastructure/torrentbox/ torrentbox:/home/john/docker-015/`. Depends on T010, T011, T013, T015.
- [ ] T017 [US1] Create real `.env` on the Pi from the credentials captured in T003: `ssh torrentbox "cat > /home/john/docker-015/.env <<'EOF'
OPENVPN_USER=<from T003>
OPENVPN_PASSWORD=<from T003>
EOF
chmod 600 /home/john/docker-015/.env"`. Verify `git check-ignore` returns true for this path (it's on the Pi, not in repo — but conceptually gitignored). Depends on T003, T016.
- [ ] T018 [US1] Create the persistent gluetun state directory on the Pi: `ssh torrentbox "mkdir -p /home/john/docker/gluetun && chmod 700 /home/john/docker/gluetun"`. Required for PIA PF token 60-day refresh (research R3). Depends on T016.
- [ ] T019 [US1] Cutover: `ssh torrentbox "cd /home/john/docker && docker compose down"`, `ssh torrentbox "sudo systemctl stop openvpn@pia"`, `ssh torrentbox "cd /home/john/docker-015 && docker compose up -d"`, `sleep 45`. This is the disruption window — schedule for a low-activity time. Depends on T017, T018.
- [ ] T020 [US1] Wait for gluetun to become healthy: `ssh torrentbox "docker ps --filter name=gluetun --format '{{.Status}}'"`. Expected `Up N seconds (healthy)` within 60 seconds. If unhealthy after 3 min, capture logs (`docker logs gluetun --tail 100`) and decide roll-forward (fix) or rollback (revert from T004 snapshot). Depends on T019.
- [ ] T021 [US1] Run `quickstart.md` **US-1 Validation** Step 1.3 (T1–T5). All five tests must PASS before this task is marked complete. T5 (`docker inspect deluge | jq '.[0].HostConfig.NetworkMode'` returns `container:...`) is the single most important one — catches the silent-bridge leak trap per research R5. Depends on T020.
- [ ] T022 [US1] Run `quickstart.md` **US-1 Validation** Steps 1.4 + 1.5 — end-to-end grab pipeline still works, LAN reachability preserved. Trigger a test grab through Sonarr or Radarr, confirm files land on NAS. Additionally verify **FR-009 (Deluge persistent state survived)**: (a) `ssh torrentbox "docker exec deluge deluge-console -c /config 'config listen_ports'"` still returns `(6881, 6891)` or whatever the pre-migration value was, (b) torrent-list count from Deluge Web UI matches the pre-migration count from T001, (c) `core.conf` fields tuned by 014 (`enc_in_policy=2`, `dht=false`, `max_connections_per_torrent=50`) still match their post-014 values. If any of these drifted, investigate before T023 (path swap). Depends on T021.
- [ ] T023 [US1] Swap live path: `ssh torrentbox "mv /home/john/docker /home/john/docker.bak-pre-015 && mv /home/john/docker-015 /home/john/docker"`. This makes the new Compose the canonical path. Future `docker compose` commands without `-f` now pick up the new stack. Depends on T022.
- [ ] T024 [US1] Update [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) — rewrite the Torrentbox VPN section to describe the sidecar topology. Move the existing "Known architectural gaps" list: gaps 1 (inverted kill-switch) and 2 (inbound on WAN) are CLOSED by this story — update their status inline. Gap 3 (port forwarding) closes in US-3. Gap 4 (no watchdog) closes in US-2. **Shared file — serialize with T036 (US-2 doc update) and T051 (US-4 doc update).** Depends on T023.

**Checkpoint**: gluetun + Deluge running in sidecar mode, kill-switch proven, pipeline flowing end-to-end, docs updated. **US-1 is independently deployable — this is the MVP slice.**

---

## Phase 4: User Story 2 - Tunnel-Health Watchdog (Priority: P2)

**Goal**: Advisor rule `vpn_leak` runs ≤ every 15 min, compares Deluge's external IP against the home-WAN denylist, emits alerts on leak, and auto-stops Deluge after 3 consecutive leak detections.

**Independent Test**: Quickstart US-2 validation (Steps 2.1 through 2.5) — green heartbeat visible, simulated leak fires an alert, 3-strike escalation stops Deluge, watchdog-down state detectable.

**Scope maps to**: FR-010, FR-011, FR-012, FR-013, FR-014, FR-023 · SC-001, SC-004, SC-005, SC-010 · Clarification Q1, Q2.

### Implementation for User Story 2

- [~] T025 [P] [US2] **DESIGN DEVIATION**: probe is implemented INLINE inside `vpn_leak.py` (not in a separate `health_checks/deluge_external_ip.py` module) because (a) the existing `HealthCheckResult` model has no JSON column for `observed_ip` (only `status`/`response_time_ms`/`error`), (b) `AlertThreshold.value` is `Numeric(10,2)` so the denylist can't live there either, (c) registering a synthetic `ServiceDefinition` with no real probe target is more abstraction than the use case warrants. Probe lives at [advisor/backend/app/services/rules/vpn_leak.py](../../advisor/backend/app/services/rules/vpn_leak.py) `_probe_external_ip()`; observed-IP state lives in module-level `_LATEST_PROBE` dict consumed by [routers/vpn.py](../../advisor/backend/app/routers/vpn.py). Denylist lives in `Settings.vpn_leak_denylist_ips` (env var). Functionally equivalent to the original design; simpler.
- [~] T026 [US2] **NOT NEEDED** per the T025 deviation. No `deluge-vpn` ServiceDefinition row is created — the probe state is module-level, not table-backed. The synthetic `target_id=0` constant on `VpnLeakRule.DELUGE_VPN_TARGET_ID` keeps engine-level dedup working without a real DB row. Either (a) add a row to the existing service table via Alembic migration, or (b) create the row at rule-engine startup if it doesn't exist (simpler; no migration). Pick (b) per Constitution II. Implement in a startup hook in [advisor/backend/app/main.py](../../advisor/backend/app/main.py) or the rule engine init. Depends on T025.
- [X] T027 [US2] Probe is invoked inline in `VpnLeakRule.evaluate()` per the T025 deviation. Cadence = `rule_engine_interval_seconds` (default 60s; well within the FR-010 ≤15 min ceiling).
- [~] T028 [US2] **DESIGN DEVIATION**: `AlertThreshold` model is `Numeric(10,2)`-only and cannot store a list of IPs. Both config knobs moved to `Settings`: `vpn_leak_denylist_ips` (comma-separated string, defaults to `"67.176.27.48"`) and `vpn_leak_escalation_threshold` (int, defaults to `3`). Override via env vars on HOLYGRAIL if needed. See [advisor/backend/app/config.py](../../advisor/backend/app/config.py).
- [X] T029 [P] [US2] Author [advisor/backend/app/services/rules/vpn_leak.py](../../advisor/backend/app/services/rules/vpn_leak.py) — the `VpnLeakRule` class per data-model.md E5. Subclass `Rule`, implement `evaluate(ctx)`: read `ctx.thresholds.get("vpn_leak_denylist_ips", [])` (prefixed key, matches the seeding in T028), read `ctx.health_results[deluge_vpn_service_id]`, emit `RuleResult` only when status is red AND `observed_ip in denylist` (**set membership, NOT substring** — see data-model.md E5 evaluate pseudocode for exact form). Yellow is a soft warning, not a result. Reading the escalation threshold: `ctx.thresholds.get("vpn_leak_escalation_threshold", 3)`.
- [X] T030 [US2] Register `VpnLeakRule` in [advisor/backend/app/services/rules/\_\_init\_\_.py](../../advisor/backend/app/services/rules/__init__.py) — add to the `RULES` list. Depends on T029.
- [X] T031 [US2] Extend the rule engine with an **escalation mechanism** for per-rule 3-strike auto-remediation (per FR-012 + Clarification Q2). Add to [advisor/backend/app/services/rule_engine.py](../../advisor/backend/app/services/rule_engine.py): track consecutive-fire counts per `(rule_id, target_id)` **in-memory only** across ticks (explicit tradeoff — see data-model.md E5 "Escalation counter persistence" note; restart-reset is accepted); when count hits the rule's `escalation_threshold` (read via `ctx.thresholds.get("vpn_leak_escalation_threshold", 3)`), invoke an `on_escalate` callback and emit a distinct `Alert` with `rule_id="<original>:remediation"`. Keep narrow to rules that opt in (default off). Depends on T030.
- [X] T032 [US2] Implement the `on_escalate` callback for `vpn_leak` — a helper that runs `ssh torrentbox docker stop deluge`. Put in [advisor/backend/app/services/remediation.py](../../advisor/backend/app/services/remediation.py) (new module). Keep the interface narrow (`stop_container(host, name)`); do NOT generalize to a "remediation framework" until a second use case demands it. Wire it into the rule via `VpnLeakRule.on_escalate = stop_container(host="torrentbox", name="deluge")`. Depends on T031.
- [X] T033 [P] [US2] Author [advisor/backend/tests/test_rule_vpn_leak.py](../../advisor/backend/tests/test_rule_vpn_leak.py) — pytest covering the six scenarios in data-model.md E5 test section (empty health_results, green, yellow, red-in-denylist → alert, three consecutive reds → escalation mocked, red-not-in-denylist). Follow the pattern of existing [test_rule_engine.py](../../advisor/backend/tests/test_rule_engine.py). Tests are written AFTER the rule per Constitution IV, but can be authored in parallel with other US-2 tasks since they live in a different file.
- [X] T033a [P] [US2] Author backend endpoint [advisor/backend/app/routers/vpn.py](../../advisor/backend/app/routers/vpn.py) — implements `GET /api/vpn-status` per contracts/README.md and data-model.md E7. Compute the 6-state summary (OK / LEAK_DETECTED / PROBE_UNREACHABLE / WATCHDOG_DOWN / AUTO_STOPPED / UNKNOWN) from latest `HealthCheckResult` for `deluge-vpn` + active `Alert` rows with `rule_id="vpn_leak"` or `"vpn_leak:remediation"` + heartbeat age. Apply the state-precedence ordering from data-model.md E7 (AUTO_STOPPED > LEAK_DETECTED > WATCHDOG_DOWN > PROBE_UNREACHABLE > OK > UNKNOWN). Register the router in [advisor/backend/app/main.py](../../advisor/backend/app/main.py). Pre-render the `message` field as a concise human-readable summary. Depends on T026 (service registration exists) and T028 (threshold rows seeded). (FR-013.)
- [X] T033b [P] [US2] Author pytest [advisor/backend/tests/test_vpn_status_endpoint.py](../../advisor/backend/tests/test_vpn_status_endpoint.py) for the new endpoint — one test per state transition (empty DB → UNKNOWN, one green HCR → OK, one yellow HCR → PROBE_UNREACHABLE, old HCR → WATCHDOG_DOWN, active vpn_leak alert → LEAK_DETECTED, active vpn_leak:remediation alert → AUTO_STOPPED). Test state precedence ordering explicitly. Depends on T033a.
- [X] T033c [P] [US2] Author frontend [advisor/frontend/src/components/VpnStatusCard.tsx](../../advisor/frontend/src/components/VpnStatusCard.tsx) + [advisor/frontend/src/components/NavStatusPill.tsx](../../advisor/frontend/src/components/NavStatusPill.tsx) + [advisor/frontend/src/services/vpn.ts](../../advisor/frontend/src/services/vpn.ts) typed client. Five-state visual rendering per data-model.md E7 "Frontend mapping" table. Inject the card at the top of [advisor/frontend/src/pages/Dashboard.tsx](../../advisor/frontend/src/pages/Dashboard.tsx) and the pill into the existing top-nav component (locate it via search — likely `Navigation.tsx` or `AppShell.tsx`; modify just that one file). Auto-refresh every 60 seconds on a simple setInterval (or match any existing polling pattern in the frontend). "View alert" button on LEAK_DETECTED / AUTO_STOPPED states deep-links to the alerts page filtered by the `active_alert_id`. Depends on T033a.
- [ ] T034 [US2] Deploy the Advisor changes to HOLYGRAIL via the existing deploy script: `bash scripts/deploy-advisor.sh`. The deploy covers backend (T025–T032 + T033a) AND frontend (T033c) in one pass. Per the memory [reference_advisor_deploy.md](/Users/jd/.claude/projects/-Users-jd-Code-camelot/memory/reference_advisor_deploy.md): never `git pull` on HOLYGRAIL. Depends on T025, T027, T028, T030, T031, T032, T033a, T033c.
- [ ] T035 [US2] Run `quickstart.md` **US-2 Validation** Steps 2.1 through 2.5, **including new Steps 2.4a (VPN status card + top-nav pill state transitions, US-2 AS-5/6/7) and 2.4b (AUTO_STOPPED rendering)**. Tick every checkbox. Step 2.4 (3-strike escalation) takes ~45 min at default cadence — plan accordingly. Restart Deluge after Step 2.4 cleanup. Depends on T034.
- [ ] T036 [US2] Update [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) — add a "Tunnel-health watchdog" subsection documenting the rule, denylist, escalation behavior, and where to view heartbeats. Mark gap 4 (no watchdog) as CLOSED. **Shared file — serialize with T024 and T051.** Depends on T035.

**Checkpoint**: Watchdog live. Silent VPN failure mode is now impossible without Deluge being auto-stopped + alerting loudly. US-2 is independently deployable on top of US-1.

---

## Phase 5: User Story 3 - PIA Port Forwarding for Inbound Peers (Priority: P3)

**Goal**: PIA-assigned forwarded port propagates automatically into Deluge's `listen_ports`. Inbound peer count goes from zero to non-zero within 24 hours.

**Independent Test**: Quickstart US-3 validation (Steps 3.1 through 3.3). Step 3.4 (rotation) is observational T+60d.

**Scope maps to**: FR-015, FR-016, FR-017, FR-018 · SC-006, SC-007.

**Note**: US-3 depends on US-1 being deployed. The `VPN_PORT_FORWARDING=on` setting was already baked into the Compose and `.env.example` during US-1 (T010, T011), so most of US-3 is **verification** rather than new implementation. The hook script (T013) is the propagation mechanism — US-3 exercises it.

### Implementation for User Story 3

- [ ] T037 [US3] Verify port-forwarding env vars are active in the deployed gluetun container: `ssh torrentbox "docker exec gluetun env | grep -E 'VPN_PORT_FORWARDING|FIREWALL'"`. Expected: `VPN_PORT_FORWARDING=on`, `VPN_PORT_FORWARDING_PROVIDER=private internet access`, `VPN_PORT_FORWARDING_UP_COMMAND=/gluetun-scripts/gluetun-port-hook.sh {{PORT}}`, `FIREWALL=on`.
- [ ] T038 [US3] Confirm the hook script is reachable from inside gluetun and executable: `ssh torrentbox "docker exec gluetun ls -la /gluetun-scripts/gluetun-port-hook.sh"`. Expected: `-rwxr-xr-x`, non-zero size. If it's missing or not `+x`, revisit T013/T016.
- [ ] T039 [US3] Run quickstart **Step 3.1** — verify a forwarded port has been obtained: `ssh torrentbox "docker exec gluetun wget -qO- http://localhost:8000/v1/openvpn/portforwarded"`. Expected: JSON containing an integer port. If the response is empty or 404, wait another 60s (port assignment can lag initial tunnel-up by up to 5 minutes on PIA) and retry. Depends on T037, T038.
- [ ] T040 [US3] Run quickstart **Step 3.2** — verify the port was pushed into Deluge: `ssh torrentbox "docker exec deluge deluge-console -c /config 'config listen_ports'"` returns `(P, P)` matching the value from T039, and `'config random_port'` returns `False`. If not, check gluetun logs (`docker logs gluetun | grep -i port.*forward`) for hook invocation errors. Depends on T039.
- [ ] T041 [US3] **Conditional on T040 failure.** If T040 shows the hook is not invoking `deluge-console` successfully, implement the pre-designed host-side systemd-timer fallback from research.md R3 ("Concrete fallback" subsection): deploy `/home/john/docker/gluetun-port-poller.sh` (script body already specified), `/etc/systemd/system/gluetun-port-poller.timer`, `/etc/systemd/system/gluetun-port-poller.service`, then `sudo systemctl enable --now gluetun-port-poller.timer`. Known 60-second propagation lag is acceptable (PIA rotations are 60-day events). Do NOT implement preemptively. After activation, re-run T040 to confirm port propagates. Depends on T040 (only if failing).
- [ ] T042 [US3] Seed a healthy public torrent (e.g., a recent Linux ISO) to exercise inbound peer connections. Use Deluge Web UI at http://192.168.10.141:8112. Record `added_at` timestamp.
- [ ] T043 [US3] Schedule the 24-hour inbound-peer check — quickstart **Step 3.3**. After 24 hours from T042, run `ssh torrentbox "docker exec deluge deluge-console -c /config 'info'"` and confirm at least one torrent shows `Peers > 0`. This task is deferred-execution — mark it complete only after the 24-hour window elapses and the check passes. Depends on T042.
- [ ] T044 [US3] **Deferred T+60d**: Observe a PIA port rotation event. At rotation, confirm new port propagates to `listen_ports` within minutes, no manual intervention. Schedule a calendar reminder 60 days out to run the check. Do NOT mark US-3 incomplete pending this — treat as a separate post-implementation observation task.

**Checkpoint**: Port forwarding operational, inbound peers materialize, ratio maintenance becomes feasible. F5.1 US-2 (paid private indexers) is now unblocked.

---

## Phase 6: User Story 4 - Decommission the Legacy Host-Level OpenVPN (Priority: P4)

**Goal**: Archive `/etc/openvpn/pia.conf` + scripts + credentials, disable `openvpn@pia`, confirm host iptables clean. Update docs to describe sidecar as the only live topology.

**Independent Test**: Quickstart US-4 validation (Steps 4.1 through 4.4).

**Scope maps to**: FR-019, FR-020, FR-021, FR-022 · SC-008, SC-009.

**Gate**: US-4 must NOT run until US-1 + US-2 have been stable for **≥ 7 consecutive days with zero watchdog alerts**. Enforce this gate manually — check Advisor's alert history for `rule_id=vpn_leak` before starting.

### Implementation for User Story 4

- [ ] T045 [US4] Verify the 7-day stability gate. Query Advisor: `curl -s 'http://advisor.holygrail/api/alerts?rule_id=vpn_leak&since=<7-days-ago-ISO>' | jq '.items | length'`. Expected: `0`. If non-zero, investigate each alert; US-4 does not proceed until the window is clean.
- [ ] T046 [US4] Disable the legacy OpenVPN service: `ssh torrentbox "sudo systemctl disable --now openvpn@pia && sudo systemctl is-enabled openvpn@pia"`. Expected: `disabled`. Depends on T045.
- [ ] T047 [US4] Verify Deluge is still routing through the sidecar (not the legacy VPN) after disable: `ssh torrentbox "docker exec deluge curl -s ifconfig.me"` — still a PIA IP. This confirms nothing in the stack quietly depended on the legacy service. Depends on T046.
- [ ] T048 [US4] Archive the legacy configuration: `ssh torrentbox "sudo mkdir -p /etc/openvpn/legacy-014 && sudo mv /etc/openvpn/pia.conf /etc/openvpn/pia-credentials.txt /etc/openvpn/vpn-up.sh /etc/openvpn/vpn-up.sh.bak-014-* /etc/openvpn/vpn-down.sh /etc/openvpn/legacy-014/ 2>&1"`. Verify: `ssh torrentbox "sudo ls /etc/openvpn/legacy-014/"`. Depends on T047.
- [ ] T049 [US4] Verify host iptables OUTPUT and INPUT chains are clean: `ssh torrentbox "sudo iptables -L OUTPUT -n --line-numbers | head -5; echo '---'; sudo iptables -L INPUT -n --line-numbers | head -5"`. Expected: both show `policy ACCEPT` with zero explicit rules. If any leftover rules remain, `sudo iptables -F OUTPUT && sudo iptables -F INPUT && sudo iptables -P OUTPUT ACCEPT && sudo iptables -P INPUT ACCEPT`. Depends on T048.
- [ ] T050 [US4] Re-verify the sidecar kill-switch is still intact after host iptables reset: re-run `quickstart.md` Step 1.3 tests T3, T4, T5. If any regress (the sidecar should be independent of host iptables, but confirming costs nothing), investigate. Depends on T049.
- [ ] T051 [US4] Update [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) — remove host-level VPN references from the Torrentbox section, keeping only a brief "Historical (decommissioned 2026-04-XX)" footnote. Mark architectural gap 1 (inverted kill-switch) as CLOSED by US-1+US-4 together. **Shared file — serialize with T024 and T036.** Depends on T050.
- [ ] T052 [US4] Update the VPN incident memory: [project_vpn_incident_2026-04.md](/Users/jd/.claude/projects/-Users-jd-Code-camelot/memory/project_vpn_incident_2026-04.md) — mark gaps 1 and 4 as CLOSED, gaps 2 and 3 as CLOSED by US-1 and US-3 respectively, and gap 5 (monitoring watchdog) as CLOSED by US-2. At this point the incident is fully resolved; update the frontmatter description accordingly. Depends on T051.

**Checkpoint**: Legacy topology fully archived, iptables clean, memory reflects closure. All four architectural gaps surfaced in the 014 incident are closed.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Secret audit, final doc review, commit hygiene.

- [ ] T053 [P] Secret audit on all committed files: `git grep -iE 'OPENVPN_USER|OPENVPN_PASSWORD|passkey|PIA_USER|PIA_PASS' -- infrastructure/ docs/ specs/015-vpn-sidecar/ advisor/`. Expected: zero matches (only the literal strings in `.env.example` and `data-model.md` / `plan.md` where they appear as field names, not values). FR-006, FR-023. Any credential leak requires `git restore` on the affected hunk and re-authoring.
- [ ] T054 [P] Verify `.env` is NOT in the repo diff: `git status infrastructure/torrentbox/ | grep -v .env.example | grep -i env`. Expected: no output.
- [ ] T055 [P] Run the cross-cutting validation block of [quickstart.md](quickstart.md) — secret audit, infrastructure directory reproducibility, memory update check.
- [ ] T056 Scan the final [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) diff: Torrentbox section describes only the sidecar topology (with a legacy footnote), watchdog is documented, all four architectural gaps are accounted for. No unrelated edits.
- [ ] T057 Schedule long-horizon observations (calendar reminders):
  - **T+24h from T042**: confirm inbound peer count > 0 (T043 completion).
  - **T+7d from T023**: stability gate met for US-4 (T045).
  - **T+60d from T023**: observe PIA port rotation handled automatically (T044).
  - **T+30d from T034**: confirm SC-001 (zero leak events for 30 consecutive days).
- [ ] T058 Create the feature commit on branch `015-vpn-sidecar` with only the repo-level changes: `infrastructure/torrentbox/` (new), `advisor/backend/app/services/health_checks/deluge_external_ip.py` (new), `advisor/backend/app/services/rules/vpn_leak.py` (new), `advisor/backend/app/services/rules/__init__.py` (modified), `advisor/backend/app/services/rule_engine.py` (modified), `advisor/backend/app/services/remediation.py` (new), `advisor/backend/app/routers/vpn.py` (new), `advisor/backend/app/main.py` (modified — service registration + router registration), `advisor/backend/tests/test_rule_vpn_leak.py` (new), `advisor/backend/tests/test_vpn_status_endpoint.py` (new), `advisor/frontend/src/components/VpnStatusCard.tsx` (new), `advisor/frontend/src/components/NavStatusPill.tsx` (new), `advisor/frontend/src/services/vpn.ts` (new), `advisor/frontend/src/pages/Dashboard.tsx` (modified), `advisor/frontend/src/components/Navigation.tsx` or equivalent top-nav (modified), `docs/INFRASTRUCTURE.md` (modified). Commit message references the spec, the four stories, and the F5.3 brief. Do NOT push until the user approves.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1, T001–T005)**: No dependencies — start immediately.
- **Foundational (Phase 2, T006–T009)**: Depends on Phase 1. **Blocks US-1 (T016+) and US-2 entirely.**
- **US-1 (Phase 3)**: Depends on Phase 2. **MVP slice — ships independently.**
- **US-2 (Phase 4)**: Depends on US-1 (needs a deployed sidecar to probe). Can be prepared in parallel (code authoring) but validated only after US-1 is live.
- **US-3 (Phase 5)**: Depends on US-1 (hook mechanism deployed). Mostly verification; minimal new code unless T040 fails.
- **US-4 (Phase 6)**: Depends on US-1 + US-2 being stable for 7 days. Hard gate at T045.
- **Polish (Phase 7)**: Depends on every user story the operator wanted to deliver.

### User Story Dependencies

- **US-1 (P1)**: Independent. MVP.
- **US-2 (P2)**: Technical dep on US-1 (something to probe); logical dep on US-1 (watchdog of no value without kill-switch).
- **US-3 (P3)**: Dep on US-1 (hook is in place). Independent of US-2.
- **US-4 (P4)**: Dep on US-1 + US-2 stability window. Independent of US-3 by code, but in practice wait for US-3 too so the sidecar has been fully exercised.

### Within Each User Story

- **US-1**: File authoring (T010–T015) is parallel per file; rsync (T016) joins; env file + state dir (T017, T018) are sequential on the Pi; cutover (T019) blocks on both; validation (T021, T022) blocks on healthy gluetun (T020); path swap (T023) after validation; docs (T024) last.
- **US-2**: Probe + rule + engine extension can be drafted in parallel (T025, T029, T033); integration is sequential (T026 → T027 → T031 → T032); deploy (T034) joins; validation (T035) last.
- **US-3**: Sequential verification (T037 → T038 → T039 → T040); contingency (T041) conditional; 24h observation (T043) is elapsed-time.
- **US-4**: Strictly sequential (T045 → T046 → T047 → T048 → T049 → T050 → T051 → T052).

### Parallel Opportunities

- **Phase 1**: T003, T004, T005 in parallel.
- **Phase 2**: T007, T008, T009 in parallel after T006.
- **Phase 3 (US-1)**: T010, T011, T013, T015 in parallel (different files). T014 blocks on T013 only.
- **Phase 4 (US-2)**: T025, T029, T033 in parallel (different files). T026 → T027 sequential. T031 → T032 sequential. T034 joins.
- **Phase 6 (US-4)**: None — strictly sequential.
- **Phase 7**: T053, T054, T055 in parallel.

### Cross-Story Parallelism

A second operator could author the US-2 code (T025, T029, T031, T032, T033) in parallel with US-1 cutover (T016–T023) — they touch different repo paths. Deployment of US-2 (T034) must wait for US-1 to be live. Single-operator default: sequential.

---

## Parallel Example: User Story 1

```bash
# Draft all the new infrastructure/torrentbox/ files concurrently (different files):
Task: "T010 Author infrastructure/torrentbox/docker-compose.yml"
Task: "T011 Author infrastructure/torrentbox/.env.example"
Task: "T013 Author infrastructure/torrentbox/gluetun-port-hook.sh"
Task: "T015 Author infrastructure/torrentbox/README.md"

# Then T014 verifies T013's shebang byte-accurately (quick check, sequential after T013).
# Then T016 rsyncs the directory — single task, joins the parallel group.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 + Phase 2.
2. Complete Phase 3 (US-1 sidecar + kill-switch).
3. **STOP and VALIDATE** via quickstart US-1 matrix. Kill-switch proven, pipeline healthy.
4. Deploy — seven-week incident class is now architecturally closed. Watchdog, port forwarding, and decommission can come later.

### Incremental Delivery

1. Phase 1 + 2 → plumbing ready.
2. US-1 → validate → **MVP shipped** (security win alone).
3. US-2 → validate → observability + auto-remediation shipped.
4. US-3 → validate → port forwarding shipped (unblocks F5.1 US-2 paid indexers).
5. Wait 7 days.
6. US-4 → validate → legacy retired.
7. Phase 7 → secret audit, docs scan, commit.

### Single-Operator Strategy (default for this project)

Camelot is single-owner per [CLAUDE.md](../../CLAUDE.md). Realistic execution:

- Session 1: Phase 1 + 2 + US-1 end-to-end (~2 hours, including quickstart validation).
- Session 2 (same day or next): US-2 implementation + deploy + validation (~2 hours).
- Session 3: US-3 verification (~30 min active, 24h observation).
- +7 days later, Session 4: US-4 + Phase 7 + commit (~1 hour).

---

## Notes

- **Shared file serialization**: T024, T036, and T051 all edit `docs/INFRASTRUCTURE.md` in different sections. Serialize strictly — do not parallelize even if stories are worked in parallel.
- **Shebang discipline**: T013 and T014 together prevent recurrence of the 014 incident class. Do not take shortcuts with `echo` or heredoc for executable scripts on the Pi. Edit through a real editor.
- **No committed secrets, ever**: PIA credentials, API keys, cookies, passkeys — none appear in any file under `/Users/jd/Code/camelot/`. `.env` lives on the Pi only.
- **Rollback discipline**: The T004 snapshot enables FR-026 rollback. Do not delete it until at least 7 days after T023 (the live-path swap).
- **Test-After**: T033 (pytest for the rule) is written AFTER T029 (the rule itself) per Constitution IV.
- **Advisor deploy**: T034 uses `bash scripts/deploy-advisor.sh` per [reference_advisor_deploy.md](/Users/jd/.claude/projects/-Users-jd-Code-camelot/memory/reference_advisor_deploy.md) — never `git pull` on HOLYGRAIL.
- **Long-horizon observations**: T043 (+24h), T045 (+7d), T044 (+60d), SC-001 check (+30d) are elapsed-time; they don't block Phase 7 commit but must be tracked on the calendar.
