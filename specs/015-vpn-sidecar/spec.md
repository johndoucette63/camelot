# Feature Specification: VPN Sidecar Migration & Kill-Switch Hardening

**Feature Branch**: `015-vpn-sidecar`
**Created**: 2026-04-14
**Status**: Draft
**Input**: User description: "F5.3 VPN sidecar migration and kill-switch hardening — migrate Deluge from host-level OpenVPN to a sidecar VPN container with proper default-deny kill-switch, PIA port forwarding, and a tunnel-health watchdog. See docs/F5.3-vpn-sidecar-migration.md."

## Clarifications

### Session 2026-04-14

- Q: Watchdog leak-detection policy — allowlist of PIA IP ranges, denylist of home WAN, or both? → A: Denylist — match against the known home WAN IP (minimum entry). Simpler, zero maintenance as PIA rotates exits, matches the exact incident failure mode.
- Q: Automated remediation default when the watchdog is confident Deluge is leaking? → A: Auto-stop Deluge after 3 consecutive leak detections plus loud alert. Fails closed. Soft warnings (probe unreachable) do not count toward the threshold.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sidecar VPN container with default-deny kill-switch (Priority: P1)

As the Torrentbox operator, I want Deluge to run inside a VPN sidecar container with a default-deny kill-switch enforced inside that container's network namespace, so that Deluge physically cannot reach the internet on any path other than the VPN tunnel — even during tunnel hiccups, container restarts, or an outright failure of the VPN process.

**Why this priority**: This is the central purpose of the feature. The current host-level OpenVPN topology produced a 7-week silent outage (2026-02-23 → 2026-04-14) during which Deluge egressed on the home WAN IP with no alert. A proper sidecar kill-switch makes that failure mode impossible: if the VPN is down, the sidecar's network namespace has no viable egress path, so Deluge simply cannot connect to peers at all. Without this story, the other three have limited value.

**Independent Test**: Deploy the sidecar, point Deluge at it via shared network namespace, and perform two checks: (a) with the tunnel up, Deluge's external IP is a PIA exit, and (b) with the sidecar stopped, Deluge's external-IP probe fails entirely (not a fallback to the home WAN IP). Can be validated without the watchdog or port forwarding stories in place.

**Acceptance Scenarios**:

1. **Given** the sidecar container is running and its VPN tunnel is established, **When** Deluge probes its external IP, **Then** the returned IP is a known PIA exit, never the home WAN IP.
2. **Given** the sidecar container is stopped or restarting, **When** Deluge attempts any outbound connection, **Then** the connection fails (no fallback egress), and no bytes leave the home WAN on Deluge's behalf.
3. **Given** the sidecar container is running but its tunnel has temporarily dropped, **When** Deluge attempts peer connections, **Then** they are blocked at the sidecar network-namespace level until the tunnel re-establishes.
4. **Given** Deluge is migrated behind the sidecar, **When** Sonarr and Radarr send torrents to Deluge and Deluge completes downloads, **Then** files arrive at `/mnt/nas/torrents/complete` and the existing *arr → Deluge → NAS → Plex flow continues to work end-to-end.
5. **Given** credentials for the VPN provider are needed by the sidecar, **When** the sidecar is configured, **Then** those credentials are supplied through a mechanism that does not commit them to the repository.

---

### User Story 2 - Tunnel-health watchdog (Priority: P2)

As the Torrentbox operator, I want an automated check that continuously verifies Deluge is actually egressing through the VPN and not the home WAN, so that any silent VPN failure produces a visible alert within minutes rather than weeks.

**Why this priority**: The sidecar kill-switch (US-1) is the primary defense, but even with that in place, a catastrophic misconfiguration or an unforeseen Docker networking change could result in unwanted behavior. The operator wants defense-in-depth with an explicit observability guarantee: the thing that's supposed to protect me must also be observable, and the watchdog itself must be observable. This story is P2 because without US-1 the kill-switch is the bigger value; with US-1 the watchdog becomes confidence-reinforcement rather than load-bearing.

**Independent Test**: Configure the watchdog, then simulate a failure by temporarily bypassing the sidecar (e.g., point a test container at the host network) and confirm the watchdog fires an alert within its stated interval. Separately, verify that if the watchdog itself stops running, its absence is detectable from the operator's existing monitoring dashboard.

**Acceptance Scenarios**:

1. **Given** Deluge is healthy and routing through the VPN, **When** the watchdog runs, **Then** it records a "healthy" heartbeat and emits no alert.
2. **Given** Deluge's external IP is observed to match the home WAN IP (or any non-PIA range), **When** the watchdog runs, **Then** it fires an alert through the existing Network Advisor alert pipeline within one check interval.
3. **Given** the watchdog has not reported a heartbeat for two consecutive intervals, **When** the operator views the monitoring dashboard, **Then** the absent heartbeat is surfaced as a distinct "watchdog down" condition, not silently ignored.
4. **Given** the watchdog detects three consecutive leak conditions, **When** the escalation threshold is reached, **Then** an automated remediation (e.g., stop the Deluge container) is triggered, and the operator is notified that remediation fired.
5. **Given** the operator opens the Advisor dashboard, **When** the VPN is healthy, **Then** a prominent green "VPN OK" card is visible at the top of the main view AND a matching status pill is visible in the top navigation on every Advisor page.
6. **Given** the watchdog detects a leak, **When** the operator is already on any Advisor page (dashboard or otherwise), **Then** the top-nav status pill switches to red within one check interval, and the dashboard card shows the observed non-VPN IP plus a link to the fired alert.
7. **Given** the watchdog has not produced a heartbeat for two consecutive intervals, **When** the operator opens the Advisor dashboard, **Then** the VPN card shows a distinct "Watchdog Down" state (gray, not green), separate and visually distinguishable from the leak state.

---

### User Story 3 - PIA port forwarding for inbound peers (Priority: P3)

As the Torrentbox operator, I want the sidecar to negotiate PIA's port-forwarded port and pass it through to Deluge automatically, so that inbound peer connections work, share ratios can actually build, and private-tracker indexers (F5.1 US-2) become viable.

**Why this priority**: PIA port forwarding is required for private-tracker participation — ratio requirements can't realistically be met without inbound peer connections. The operator has deferred F5.1 US-2 (paid private indexers) until this is in place. Ranked P3 because US-1 + US-2 together already deliver the security and observability wins; port forwarding is the capability unlock for the next feature rather than a safety fix.

**Independent Test**: With the sidecar and kill-switch in place, enable port forwarding, wait for PIA to assign a port, verify that port is reflected in Deluge's configuration, and observe that inbound peer connection count on a healthy public torrent goes from zero to non-zero within 24 hours.

**Acceptance Scenarios**:

1. **Given** the sidecar supports PIA port forwarding, **When** the tunnel establishes, **Then** a forwarded port is assigned by PIA and visible in the sidecar's logs or status.
2. **Given** PIA has assigned a forwarded port, **When** Deluge queries for its listen port, **Then** Deluge's active listen port matches the PIA-assigned port (reconciled automatically, not set manually).
3. **Given** a 24-hour observation window on a well-seeded public torrent after port forwarding is active, **When** Deluge's peer-connection history is reviewed, **Then** incoming peer connections are non-zero (contrast with zero inbound connections pre-feature).
4. **Given** PIA rotates the forwarded-port token (ports are time-limited), **When** the rotation occurs, **Then** the new port is propagated to Deluge automatically, with no manual intervention and no sustained disruption to ongoing torrents.

---

### User Story 4 - Decommission the legacy host-level OpenVPN (Priority: P4)

As the Torrentbox operator, I want the legacy host-level OpenVPN configuration archived and disabled once the sidecar has been proven stable for a week, so that there is only one source of truth for VPN topology and no one can accidentally re-enable the broken-by-design kill-switch model.

**Why this priority**: Pure cleanup. The sidecar must run in parallel with the legacy OpenVPN during the migration (the sidecar handles VPN for Deluge; the legacy service stays disabled but config stays on disk). After a stabilization window, removing the legacy pieces eliminates a class of confusion and prevents accidental reversion. Ranked P4 because it's the last step and is intentionally gated on a stability-proof window.

**Independent Test**: After the sidecar has run for at least 7 continuous days with no watchdog alerts, the legacy `openvpn@pia.service` is disabled, its configuration archived, and the host iptables state confirmed as clean defaults. Can be rolled back by restoring from the archive if anything regresses.

**Acceptance Scenarios**:

1. **Given** the sidecar has operated successfully for at least 7 consecutive days, **When** the legacy host OpenVPN service is disabled, **Then** Deluge continues to function correctly through the sidecar.
2. **Given** the legacy configuration files are archived, **When** an operator or future script inspects `/etc/openvpn/`, **Then** the active files are clearly separated from archived ones (e.g., under a `legacy-014/` subdirectory) and no live references point at them.
3. **Given** the host iptables state after decommissioning, **When** inspected, **Then** it shows default-ACCEPT chains with zero rules — no leftover kill-switch fragments.
4. **Given** the Torrentbox infrastructure documentation, **When** a new operator reads it, **Then** the only VPN topology described is the sidecar; no references remain to host-level OpenVPN except as historical context.

---

### Edge Cases

- **Sidecar crash and restart**: If the sidecar container crashes, Deluge should pause (network namespace gone) rather than fall back to host networking. After sidecar restarts, Deluge should recover automatically on the sidecar's next healthy state.
- **PIA forwarded-port rotation**: PIA's forwarded ports have a time-limited token (historically ~2 months). The port must be renewed before expiry without manual intervention; failure to renew must surface as an alert.
- **Docker daemon restart**: After a reboot or `systemctl restart docker`, the sidecar must start before Deluge attaches to its network namespace. Start ordering and restart policies must be correct.
- **In-flight torrents during migration**: Active downloads at cutover time should survive the container switch. The `move_completed` configuration already separates the torrent session from the final file storage, so files are durable, but Deluge may lose its in-flight torrent state. Operator acknowledges a brief service disruption.
- **Sidecar log verbosity leaking credentials**: The sidecar must not print VPN credentials into logs at any verbosity level suitable for normal operation.
- **Watchdog false positive from probe-target outage**: If the IP-echo service used by the watchdog is itself unreachable, the watchdog must distinguish "probe target down" from "Deluge leaking" and not fire a leak alert when it cannot determine Deluge's actual egress IP.
- **LAN access regression**: Sonarr, Radarr, Prowlarr, and the Mac workstation must continue to reach Deluge's Web UI and daemon RPC ports on the LAN after migration. The sidecar's port mapping must preserve LAN-reachability without opening Deluge to the wider internet.
- **NAS bind mount inheritance**: Deluge must retain its bind mount at `/mnt/nas/torrents` after the network-mode change. If the mount is missing post-migration, downloads have nowhere to land.
- **Rollback window**: If the sidecar reveals an unresolvable issue within the first 7 days, the operator must be able to re-enable the legacy host OpenVPN and revert Deluge to its prior network mode in under an hour.

## Requirements *(mandatory)*

### Functional Requirements

#### Sidecar + Kill-Switch

- **FR-001**: The system MUST run the VPN tunnel for Deluge inside a dedicated sidecar container, replacing the host-level `openvpn@pia.service` as the VPN mechanism for Deluge's traffic.
- **FR-002**: Deluge MUST share the sidecar's network namespace (or an equivalent topology that produces the same guarantee) so that all of Deluge's outbound traffic is subject to the sidecar's routing.
- **FR-003**: The sidecar MUST enforce a default-deny network policy: outbound traffic is blocked by default and explicitly allowed only to the LAN (192.168.10.0/24) and to the VPN tunnel interface.
- **FR-004**: When the sidecar's VPN tunnel is not established, Deluge MUST be unable to reach any host outside the LAN, including during sidecar startup, tunnel renegotiation, and tunnel failure.
- **FR-005**: The sidecar's image MUST be pinned to a specific tag, not `:latest`, to prevent unattended image pulls from introducing regressions.
- **FR-006**: VPN credentials MUST NOT be committed to the repository. They are supplied to the sidecar through a gitignored file or equivalent mechanism stored only on the Torrentbox.
- **FR-007**: The existing \*arr → Deluge → NAS → Plex workflow MUST continue to function end-to-end after migration, including Sonarr/Radarr sending torrents, Deluge downloading and moving completed files, and \*arr importing into the library.
- **FR-008**: LAN hosts (Sonarr, Radarr, Prowlarr, the Mac workstation) MUST continue to reach Deluge's Web UI and daemon RPC ports after migration.
- **FR-009**: Deluge's persistent state (torrent list, config) MUST survive the migration. The operator may lose in-flight session state for a brief cutover window but not settings or the torrent queue on disk.

#### Tunnel-Health Watchdog

- **FR-010**: A watchdog MUST check Deluge's external egress IP at least every 15 minutes. If the observed IP matches any entry in a denylist (minimum required entry: the home WAN IP), the watchdog MUST treat this as a leak condition. The denylist MAY be extended by the operator but MUST NOT fall below the home-WAN-IP baseline.
- **FR-011**: When the watchdog detects a leak (egress IP is not a VPN exit), it MUST emit an alert through the existing Network Advisor alert pipeline.
- **FR-012**: After three consecutive leak detections (as defined by FR-010), the watchdog MUST stop the Deluge container and emit a distinct "remediation fired" alert in addition to the per-check leak alerts. Soft warnings from FR-014 (e.g., probe endpoint unreachable) MUST NOT count toward the three-strike threshold.
- **FR-013**: The VPN tunnel health MUST be **prominently and continuously** visible on the Advisor dashboard. Specifically: (a) a dedicated "VPN Status" card appears at the top of the main dashboard view; (b) a persistent status pill is visible in the Advisor's top navigation on every page; (c) both surfaces reflect the current state within one check interval of any change. The five states MUST be distinguishable at a glance: **OK** (green — tunnel up, exit IP shown, probe timestamp), **LEAK DETECTED** (red banner — non-VPN IP observed, link to alert), **PROBE UNREACHABLE** (yellow — probe soft-warning per FR-014, neither OK nor a leak), **WATCHDOG DOWN** (gray — no heartbeat for ≥ 2 intervals, distinct from leak), **AUTO-STOPPED** (red with action badge — Deluge stopped by escalation per FR-012). The watchdog's last successful run timestamp MUST be visible from the card.
- **FR-014**: The watchdog MUST distinguish between "probe endpoint is unreachable" and "Deluge is leaking"; the former is a soft warning, the latter is a hard alert.

#### PIA Port Forwarding

- **FR-015**: The sidecar MUST request a PIA-forwarded port automatically once the tunnel is established, without manual operator action.
- **FR-016**: The PIA-assigned forwarded port MUST be propagated automatically to Deluge's listen-port configuration, so that Deluge's active listen port matches the PIA-assigned port at all times.
- **FR-017**: When PIA rotates the forwarded-port token, the new port MUST be propagated to Deluge automatically without requiring a restart of the operator.
- **FR-018**: After 24 hours of operation with port forwarding active, inbound peer connection count on a healthy public torrent MUST be non-zero.

#### Legacy Decommission

- **FR-019**: After the sidecar has operated without watchdog alerts for at least 7 consecutive days, the legacy `openvpn@pia.service` MUST be disabled on the Torrentbox host.
- **FR-020**: The legacy VPN configuration (`pia.conf`, `vpn-up.sh`, `vpn-down.sh`, `pia-credentials.txt`) MUST be archived rather than deleted — moved to a clearly-labeled subdirectory (e.g., `/etc/openvpn/legacy-014/`) that is no longer on any live code path.
- **FR-021**: After decommission, the host iptables OUTPUT and INPUT chains MUST show default-ACCEPT policies with zero explicit rules (no leftover kill-switch fragments).
- **FR-022**: Project documentation (`docs/INFRASTRUCTURE.md` and relevant memory files) MUST be updated to describe only the sidecar topology as current, with legacy references retained only as historical context.

#### Cross-cutting

- **FR-023**: All infrastructure changes MUST be captured in repo-committed configuration (Docker Compose updates, scripts, documentation) so that the Torrentbox can be reproduced from the repo.
- **FR-024**: The feature MUST NOT migrate Sonarr, Radarr, Prowlarr, FlareSolverr, Lidarr, or LazyLibrarian. Only Deluge changes network mode.
- **FR-025**: The feature MUST NOT change the VPN provider (remains PIA) or the `/mnt/nas/torrents` SMB mount behavior.
- **FR-026**: A rollback path MUST exist: within the first 7 days, the operator can re-enable `openvpn@pia.service`, revert Deluge's Docker Compose definition, and restore prior behavior within one hour. The rollback procedure MUST be documented.

### Key Entities

- **VPN Sidecar Container**: A containerized VPN client that Deluge shares a network namespace with. Attributes: image (pinned tag), credentials (gitignored), VPN provider settings, exposed Deluge ports, health status, port-forward state, log verbosity. Replaces the host-level `openvpn@pia.service` for Deluge's purposes.
- **Kill-Switch Policy**: A default-deny firewall ruleset enforced inside the sidecar's network namespace. Attributes: allowed destinations (LAN + VPN tunnel), default action (drop), not configurable at runtime from outside the container.
- **Tunnel-Health Watchdog**: A scheduled check that validates Deluge's external egress IP. Attributes: interval, known-good IP range policy, leak threshold before escalation, alert sink, heartbeat record, escalation action.
- **PIA Forwarded Port**: A time-limited port assignment obtained from PIA's port-forwarding API. Attributes: port number, expiry timestamp, renewal state. Propagated into Deluge's listen-port configuration automatically.
- **Legacy VPN Archive**: The decommissioned host-level OpenVPN configuration, relocated to a clearly-labeled archive path, retained for rollback only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero observed instances of Deluge egress on the home WAN IP for at least 30 consecutive days after migration (measured by the watchdog's leak counter; a single false positive investigated and dismissed is acceptable but leak-counter resets must be justified).
- **SC-002**: When the sidecar container is stopped, Deluge's external-IP probe fails within 10 seconds (connection refused or timeout) and never returns the home WAN IP.
- **SC-003**: The existing *arr → Deluge → NAS → Plex pipeline completes at least 20 successful grabs end-to-end in the first 7 days post-migration, matching or exceeding the pre-migration baseline grab success rate.
- **SC-004**: The watchdog detects and alerts on a simulated leak (operator-induced test) within one check interval (≤15 minutes), and the alert is visible in the Network Advisor dashboard.
- **SC-005**: A deliberate simulated watchdog outage (stop the scheduled check) is detected as "watchdog down" in the monitoring dashboard within two missed intervals, distinct from a "Deluge leak" alert.
- **SC-006**: Within 24 hours of PIA port forwarding activation, Deluge's inbound peer connection count is at least 1 on a healthy public torrent (contrast with zero pre-feature).
- **SC-007**: PIA port rotation is handled without operator intervention: across at least one rotation event, Deluge's listen port is updated and downloads continue without a multi-hour disruption.
- **SC-008**: After decommissioning the legacy host OpenVPN, host iptables OUTPUT/INPUT chains show default-ACCEPT with zero explicit rules, verifiable via a single command.
- **SC-009**: Rollback to the legacy configuration, if needed within the first 7 days, completes in under 60 minutes from decision to verified Deluge-through-legacy-VPN behavior.
- **SC-010**: `docs/INFRASTRUCTURE.md`, read cold, is sufficient for a new operator to understand the current sidecar topology, verify tunnel health, and operate the watchdog — without needing to read any prior feature's spec.

## Assumptions

- The Torrentbox (Raspberry Pi 5) has sufficient CPU and memory headroom to run one additional small container (sidecar) alongside the existing seven. Baseline measurements from the current stack support this.
- The PIA subscription remains active, and the existing credentials (already stored on the Pi in `/etc/openvpn/pia-credentials.txt`) are reusable by the sidecar container without requiring a new account.
- The VPN protocol stays OpenVPN during this feature. A switch to WireGuard is a planning-phase decision informed by available sidecar support; it does not change the spec's functional requirements.
- The Network Advisor alert pipeline (delivered in Phase 4.5) is the canonical alert sink for this feature. If the Advisor is offline, watchdog alerts degrade gracefully to local logs, not to silent loss.
- The *arr stack already communicates with Deluge via LAN hostnames or container DNS that are unaffected by Deluge's network mode change, provided the sidecar's port mapping preserves LAN-reachability.
- Operator is willing to accept a brief cutover disruption during migration (target: minutes, not hours) in exchange for the security win. In-flight downloads may need to be re-queued.
- The watchdog runs on the Torrentbox itself or on HOLYGRAIL via the existing monitoring stack; this is an implementation decision deferred to `/speckit.plan`, but both are compatible with the spec.
- Private-tracker participation (F5.1 US-2) is the motivating downstream use case for port forwarding. If that use case is abandoned, US-3 remains valuable for general seeding capability but could be de-prioritized.
- The operator's storage-conscious quality profile (F5.1 US-1) and no-seed-after-complete Deluge policy are unaffected by this feature. The sidecar migration is an orthogonal concern.
