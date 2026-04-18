# Feature Specification: Tailscale Remote Access

**Feature Branch**: `018-tailscale-remote-access` *(to be created when /speckit.plan runs)*
**Created**: 2026-04-18
**Status**: Draft
**Input**: User wants to access Frigate UI (and other Camelot LAN services) remotely without exposing ports to the public internet. Surfaced as a follow-up during the 017-frigate-nvr deploy when notification tap-targets pointed at `http://192.168.10.129:5000` — works on LAN, doesn't work over cellular today.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Tap a Frigate notification from outside the house and see the live doorbell feed (Priority: P1)

As a household member who's not at home, when I tap a Frigate person-detection or package-detection notification, the Frigate web UI loads and shows the live feed and recent events — exactly the same experience I get on the home Wi-Fi. No "this only works at home" surprise.

**Why this priority**: This is the entire reason for the feature. The 017-frigate-nvr deploy's tap-target URL (`http://192.168.10.129:5000`) works on LAN but silently fails over cellular. Until that round-trip works remote, the doorbell notifications are LAN-only — a regression vs the cloud-camera UX many household members are used to.

**Independent Test**: Disconnect from home Wi-Fi (use cellular or a coffee shop). Tap the most recent Frigate notification on your phone. Frigate UI loads and the live doorbell feed plays. Total time from tap to live frame visible: under 5 seconds.

**Acceptance Scenarios**:

1. **Given** Tailscale is installed on HOLYGRAIL with subnet routing enabled for `192.168.10.0/24` and on the household member's phone, **When** they tap a Frigate notification while on cellular, **Then** the URL `http://192.168.10.129:5000` resolves and loads the Frigate UI within 5 seconds.
2. **Given** the household member opens any other Camelot service URL (e.g., `http://grafana.holygrail`, `http://advisor.holygrail`), **When** they're remote, **Then** the URL resolves over Tailscale's MagicDNS (or via a fallback hosts entry) and the service loads.
3. **Given** Tailscale is uninstalled or signed out on the phone, **When** they tap the same notification, **Then** the URL fails (expected behavior — this is the gating mechanism, not a regression).

---

### User Story 2 — All household iOS devices on Tailscale without per-device admin (Priority: P1)

As the Camelot admin, I install the Tailscale app on each household device once (mine, wife's iPad, household iPad, etc.), each device authenticates against the family Tailnet, and from then on every Camelot LAN URL works on every device whether at home or away. No SSH-to-each-Pi to install Tailscale; no per-app config; no surprise breakage when iOS auto-updates.

**Why this priority**: Without per-device install Tailscale doesn't deliver remote access for the household. With it, the marginal cost of adding a future device is one app install + one tap "sign in".

**Independent Test**: A household member's iOS device fresh out of the box (or post-factory-reset) gets Tailscale installed via the App Store, signed in with the family Tailscale account, and immediately reaches `http://192.168.10.129:5000` from cellular without any further config.

**Acceptance Scenarios**:

1. **Given** the family Tailscale account exists, **When** a new iOS device installs the Tailscale app and signs in with that account, **Then** the device joins the Tailnet and can reach all `192.168.10.0/24` addresses transparently.
2. **Given** all 4 household iOS devices are on Tailscale, **When** any of them taps a Frigate notification while remote, **Then** the link works on all of them with no per-device adjustment.

---

### User Story 3 — SSH and admin access to HOLYGRAIL + Pis from outside (Priority: P2)

As the Camelot admin, when I'm not at home, I can `ssh holygrail`, `ssh torrentbox`, `ssh nas`, etc. from my MacBook to fix things or check status — same SSH config aliases, same key auth, no separate "remote SSH" workflow.

**Why this priority**: Useful but not a release gate. The household-facing UX (US-1, US-2) is the primary value; admin SSH is a nice-to-have for the one admin (JD).

**Independent Test**: From the MacBook on cellular tethering, run `ssh holygrail` and `ssh torrentbox`. Both connect within 5 seconds using the existing `~/.ssh/config` aliases.

**Acceptance Scenarios**:

1. **Given** Tailscale is installed on the MacBook and HOLYGRAIL advertises `192.168.10.0/24`, **When** the admin SSHes to any Camelot device from outside the LAN, **Then** the SSH connection succeeds with the existing key auth — no Tailscale-specific keys, no separate hostnames.
2. **Given** the existing `bash scripts/pi-status.sh` and `bash scripts/pi-update.sh` scripts use the same SSH aliases, **When** the admin runs them from outside the LAN, **Then** they work identically to running them from inside.

---

### User Story 4 — Sealed against the public internet by default (Priority: P1)

As a security-conscious admin, I do not want to ever open a public-internet port on the home router for any Camelot service. All remote access happens over the Tailnet (encrypted WireGuard tunnel between authenticated devices, no public-facing service). The router's port-forwarding table stays empty for Camelot.

**Why this priority**: This is the constitutional promise. Constitution I (Local-First) says "data never leaves the LAN unless the owner explicitly chooses otherwise (e.g., VPN, Tailscale)". The whole reason we're picking Tailscale over a port-forward + reverse-proxy is to honor that.

**Independent Test**: From an external host that is NOT on the Tailnet, attempt to reach `<home WAN IP>:5000`, `<home WAN IP>:8123`, etc. All must time out or refuse — no service should be reachable. Run `nmap` against the home WAN IP from outside; only well-known ports the household ISP/router intentionally exposes (if any) appear.

**Acceptance Scenarios**:

1. **Given** the Tailscale deploy is complete, **When** the admin checks the router admin UI's port-forwarding table, **Then** no Camelot ports are forwarded.
2. **Given** an external scan against the home WAN IP, **When** the scan completes, **Then** no Camelot service ports respond.

---

### User Story 5 — Future-proof: same URLs work LAN and remote (Priority: P2)

As the admin maintaining HA automations, dashboards, and notifications, the URLs I bake into configurations (`http://192.168.10.129:5000`, `http://frigate.holygrail`, etc.) work identically whether the user is on home Wi-Fi or remote on cellular. Notifications already-deployed in the 017-frigate-nvr feature do not need URL rewrites once Tailscale lands.

**Why this priority**: Avoids URL migration churn across the project. The 017 feature shipped notification URLs that work on LAN; this feature should make them work everywhere without revisiting them.

**Independent Test**: All notification tap-targets and HA-dashboard hyperlinks defined in the 017 feature's `contracts/ha-automations.yaml` work unchanged from a remote device after the 018 deploy.

**Acceptance Scenarios**:

1. **Given** an HA automation references `http://192.168.10.129:5000`, **When** the device tapping the notification is on the Tailnet (LAN or remote), **Then** the URL resolves and loads — no URL conditionalization needed.
2. **Given** the household has Tailscale's MagicDNS enabled, **When** users open a `*.holygrail` hostname (defined in Pi-hole), **Then** it resolves correctly. (Note: see Open Questions — Pi-hole + Tailscale DNS interaction may need verification.)

---

### Edge Cases

- **Tailscale outage**: the cloud control plane is unreachable. Existing Tailnet device-to-device connections continue working (WireGuard data plane is direct), but new connections may not authenticate. Acceptable — this is a known Tailscale property.
- **Phone signs out of Tailscale**: notifications still arrive (HA push delivery is independent of Tailscale), but tap-target URLs fail with a connection error. The user should know to re-sign-in. Out of scope to auto-recover.
- **HOLYGRAIL goes offline**: subnet routing dies; entire LAN becomes unreachable from Tailnet. The fallback would be a second subnet router on a Pi, but that's out of scope for Phase 1 (single subnet router is acceptable for a single-admin household).
- **DNS conflict**: Pi-hole serves `*.holygrail` names on the LAN; Tailscale's MagicDNS serves Tailnet hostnames. If both are enabled on a remote device, there's potential for split-brain DNS. Need to verify Pi-hole entries still resolve via the subnet route + LAN DNS forwarding, or disable Tailscale's MagicDNS in favor of pure subnet routing.
- **NAT type incompatibility**: very rare residential NAT setups can prevent Tailscale's direct connections, falling back to relay (DERP). Fallback works but is slower; acceptable degradation.
- **Tailnet account compromise**: an attacker gaining the family Tailscale account credentials gets full LAN access. Mitigation: enable Tailscale's mandatory MFA on the account.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Tailscale (or equivalent zero-trust mesh VPN, e.g. Headscale self-hosted) MUST be installed on HOLYGRAIL with subnet routing advertising `192.168.10.0/24`.
- **FR-002**: Each household iOS/macOS device that needs remote access MUST have the Tailscale app installed and authenticated against the family Tailnet.
- **FR-003**: All `192.168.10.0/24` LAN addresses MUST be reachable from any authenticated Tailnet member, regardless of physical network location.
- **FR-004**: All `*.holygrail` hostnames (resolved by Pi-hole on the LAN) MUST resolve correctly from Tailnet members. Either via Pi-hole DNS reachable through the subnet route, or via duplicate entries in Tailscale's MagicDNS.
- **FR-005**: No Camelot service port MUST be forwarded on the home router to the public internet as part of this feature. The router's port-forwarding table for Camelot stays empty.
- **FR-006**: SSH access to HOLYGRAIL and all Pis (Torrentbox, NAS, media server) MUST work from a Tailnet-authenticated MacBook using the existing `~/.ssh/config` aliases — no Tailscale-specific keys or hostnames required.
- **FR-007**: Mandatory MFA MUST be enabled on the family Tailscale account.
- **FR-008**: Existing notification URLs in HA automations (e.g., `http://192.168.10.129:5000`) MUST work unchanged from Tailnet members; no URL rewrites required as part of this feature.
- **FR-009**: Tailscale ACLs MUST be configured so that all family Tailnet members have access to the Camelot subnet (no per-user restriction needed; single household trust boundary).
- **FR-010**: A re-install / re-onboard runbook MUST be documented in `docs/` covering: install Tailscale on a new device, sign in with family account, verify reachability — short enough for a non-technical household member to follow.

### Key Entities

- **Tailnet**: The Tailscale network grouping all authenticated devices. One per household account. Provides the encrypted WireGuard mesh.
- **Subnet Router**: HOLYGRAIL, configured to advertise the LAN subnet. The single point through which Tailnet traffic reaches non-Tailscale-installed LAN devices (the doorbell, NAS, Pis).
- **Tailnet Member Device**: Each phone/laptop/iPad with the Tailscale app installed and signed in. Reaches the Tailnet directly.
- **MagicDNS** (optional): Tailscale's built-in DNS for Tailnet hostnames. May or may not be used depending on the Pi-hole interaction tested in clarify phase.
- **Tailscale ACL**: Policy file defining who-can-reach-what within the Tailnet. For Phase 1, simple "all members reach everything" policy.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a phone on cellular (verified by checking the phone is NOT on home Wi-Fi), tapping a Frigate person-detection notification loads the Frigate UI live feed within **5 seconds** at the 95th percentile.
- **SC-002**: All four household iOS devices reach `http://192.168.10.129:5000` from cellular within **3 seconds** of opening the URL.
- **SC-003**: An external nmap scan of the home WAN IP shows **zero Camelot service ports** open. (Pre-existing, non-Camelot ports the ISP/router exposes are not in scope.)
- **SC-004**: From the MacBook on cellular tethering, `ssh holygrail` connects in **under 5 seconds** using existing `~/.ssh/config` aliases — no SSH config changes required.
- **SC-005**: A household member with no Tailscale knowledge can install + onboard a new iOS device by following `docs/tailscale-onboarding.md` in **under 5 minutes** without coaching.
- **SC-006**: Over a 30-day run, Tailscale reachability for the household-facing URLs sustains **≥ 99% availability** (subject to home internet uptime, which is the actual ceiling).

## Assumptions

- **Vendor choice**: Tailscale's hosted control plane is acceptable (free tier covers up to 100 devices and 3 users — comfortably fits a household). Headscale self-hosted is the alternative; deferred unless the user prefers it.
- **MagicDNS interaction with Pi-hole**: untested; will be resolved in `/speckit.clarify` or `/speckit.plan` research. Fallback if MagicDNS conflicts: rely purely on subnet routing + Pi-hole LAN DNS reaching via the subnet route.
- **Subnet router redundancy**: single router (HOLYGRAIL) is acceptable for Phase 1. If HOLYGRAIL is down, the household loses Camelot remote access — no different from being unable to use Camelot when HOLYGRAIL is down at home anyway.
- **Notification deep-link compatibility**: HA Companion App on iOS opens absolute URLs in its in-app browser. This was verified during the 017 deploy. Tailscale doesn't change this behavior — the URL just becomes reachable.
- **No business-tier Tailscale features required**: ACLs, exit nodes, file sync, taildrop — all optional or out of scope for Phase 1.
- **Family account model**: a single shared "household" account is acceptable for the household trust boundary, OR each member uses their own account on a shared Tailnet (Tailscale supports both). The clarify phase decides which.
- **Constitution alignment**: Tailscale is the intended remote-access mechanism per Constitution I — "data never leaves the LAN unless the owner explicitly chooses otherwise (e.g., VPN, Tailscale)". This feature is the explicit "owner choice" referenced in that principle.

---

## Notes on relationship to feature 017

The 017-frigate-nvr deploy explicitly deferred remote access:
- Spec assumption: "Network trust boundary: The local network (192.168.10.0/24) is trusted; the NVR web UI does not need its own authentication gate within Phase 1. Remote access and auth hardening are explicitly deferred to a separate feature."
- Notification tap-target URL: `http://192.168.10.129:5000` (LAN-reachable today, Tailnet-reachable after this 018 deploys).

When 018 ships, the 017 notifications "just work" remotely. No 017 contract changes required.

---

*Spec-kit compatible. Use `/speckit.clarify` to resolve open clarifications (subnet router redundancy, MagicDNS vs Pi-hole, family account model), then `/speckit.plan` to design the deploy.*
