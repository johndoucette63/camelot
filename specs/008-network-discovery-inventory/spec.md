# Feature Specification: Network Discovery & Device Inventory

**Feature Branch**: `008-network-discovery-inventory`  
**Created**: 2026-04-09  
**Status**: Draft  
**Input**: User description: "@docs/F4.2-network-discovery.md"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scan LAN and Populate Device List (Priority: P1)

The admin opens the advisor and sees every device currently or recently connected to the home network — IP address, hostname, MAC address, hardware vendor, and when it was last detected. This happens automatically without any manual action; the system periodically scans the network and updates the list.

**Why this priority**: Without discovered devices, none of the other inventory features have data to work with. This is the foundation of the entire feature.

**Independent Test**: Can be fully tested by observing that the device list populates with accurate network data matching what a manual scan would show, delivering a real-time network picture.

**Acceptance Scenarios**:

1. **Given** the advisor is running and the network is active, **When** a scheduled scan completes, **Then** all reachable devices on 192.168.10.0/24 appear in the inventory with IP, hostname (if resolvable), MAC address, vendor name, and last-seen timestamp.
2. **Given** a device is on the network, **When** the scan interval elapses (default 15 minutes), **Then** the device's last-seen timestamp is refreshed in the inventory.
3. **Given** a device was present in a previous scan, **When** it does not respond in the current scan, **Then** it remains in the inventory but its online status reflects it is no longer reachable.

---

### User Story 2 - View Device Inventory in Dashboard (Priority: P2)

The admin visits a dedicated device inventory page in the advisor dashboard and sees a complete, sortable, filterable list of all known devices — both currently online and previously seen — with clear visual indicators of their status.

**Why this priority**: Visibility is the first step toward management. The list view gives the admin a quick health check of the network without requiring any deeper interaction.

**Independent Test**: Can be fully tested by viewing the device list page and confirming all discovered devices appear with correct data and status indicators.

**Acceptance Scenarios**:

1. **Given** devices have been discovered, **When** the admin loads the inventory page, **Then** each device row shows: IP address, hostname, MAC address, vendor, last-seen timestamp, and an online/offline status indicator.
2. **Given** a device is responding to the most recent scan, **When** viewing the list, **Then** it shows a green online indicator; devices not seen in the last scan show a gray offline indicator.
3. **Given** a list of 20+ devices, **When** the admin sorts by any column or filters by hostname or IP, **Then** the list updates immediately to reflect the chosen order or filter.
4. **Given** known Camelot infrastructure devices (HOLYGRAIL, Torrentbox, NAS, Pi-hole, Mac), **When** viewing the list, **Then** these devices are visually distinguished from unknown devices.

---

### User Story 3 - Annotate Devices with Roles and Descriptions (Priority: P3)

The admin clicks on any device to assign it a role (e.g., server, IoT, workstation, printer), a human-readable description, and optional free-form tags. These annotations persist and are visible in the device list and available to the AI advisor as context.

**Why this priority**: Annotations transform raw scan data into meaningful inventory. They enable the AI advisor to give relevant, context-aware recommendations instead of treating every device as unknown.

**Independent Test**: Can be fully tested by annotating a device and verifying the annotation persists across page reloads and appears in the device list view.

**Acceptance Scenarios**:

1. **Given** any device in the inventory, **When** the admin clicks it and assigns a role and description, **Then** the annotation is saved and immediately visible in the device list without requiring a new scan.
2. **Given** the advisor launches for the first time, **When** known Camelot devices are discovered, **Then** they are pre-populated with default annotations (e.g., HOLYGRAIL: role=server, Torrentbox: role=server, NAS: role=storage, Pi-hole: role=dns).
3. **Given** an annotated device, **When** an AI chat session is started, **Then** the device's role, description, and tags are available as context for the AI.

---

### User Story 4 - Detect New and Missing Devices (Priority: P4)

The admin sees clear notifications in the dashboard when a device that has never been seen before appears on the network, or when a previously known device stops responding for multiple consecutive scan cycles.

**Why this priority**: Alerting on changes is what makes the inventory actionable rather than just informational. New unknown devices may indicate unauthorized access; missing known devices indicate outages.

**Independent Test**: Can be fully tested by connecting a new device to the network and verifying an event appears in the event log within one scan cycle.

**Acceptance Scenarios**:

1. **Given** a device appears on the network that has no prior record in the inventory, **When** a scan detects it, **Then** a "new device" event is logged with the device details and timestamp.
2. **Given** a known device was online in the last scan, **When** it fails to respond in 2 or more consecutive scans, **Then** it is flagged as offline and an "offline" event is logged.
3. **Given** events have been logged, **When** the admin views the event history page, **Then** all new-device, offline, and back-online events are listed with timestamps and device identifiers, newest first.
4. **Given** events exist in the system, **When** an AI chat session is active, **Then** recent events (last 24 hours) are available as context for AI recommendations.

---

### Edge Cases

- What happens when a device's IP changes between scans (DHCP reassignment without reservation)?
- How does the system handle a device that appears with a different MAC on the same IP (VM/container bridge interfaces)?
- What happens when the scan host cannot reach the network at all (network error or host isolation)? → Cycle is skipped, a scan-error event is logged, device statuses are unchanged.
- How does the system handle a hostname that resolves to multiple IPs?
- What if two devices report the same MAC address (VM bridging, network equipment quirks)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically scan 192.168.10.0/24 on a configurable interval, defaulting to every 15 minutes.
- **FR-002**: Each discovered device MUST be recorded with IP address, hostname (if resolvable), MAC address, hardware vendor (derived from MAC prefix), and last-seen timestamp.
- **FR-003**: System MUST persist the device inventory so that devices remain visible even when offline.
- **FR-004**: System MUST detect devices not previously in the inventory as new and log a timestamped new-device event.
- **FR-005**: System MUST flag devices that miss 2 or more consecutive *successful* scan cycles as offline and log a timestamped offline event.
- **FR-005b**: When a device that was flagged offline responds to a subsequent scan, the system MUST update its status to online and log a timestamped back-online event.
- **FR-005a**: When a scan fails to complete (process error, network unreachable), the system MUST skip that cycle without updating any device statuses and MUST log a scan-error event with a timestamp and error detail.
- **FR-006**: Users MUST be able to view all discovered devices in a sortable, filterable list showing IP, hostname, MAC, vendor, last-seen, and online/offline status.
- **FR-007**: Known Camelot devices MUST be visually distinguished from unrecognized devices in the device list.
- **FR-008**: Users MUST be able to assign a role, description, and tags to any device; these annotations MUST persist.
- **FR-009**: System MUST pre-populate annotations for known Camelot devices on first discovery.
- **FR-010**: Device annotations (role, description, tags) MUST be accessible as context for the AI advisor.
- **FR-011**: Users MUST be able to view an event history log showing new-device, offline, back-online, and scan-error events with timestamps; events older than 30 days MUST be automatically purged.
- **FR-012**: Recent events (last 24 hours) MUST be available as context for the AI advisor.

### Key Entities

- **Device**: Represents a network endpoint. MAC address is the canonical identity key — a device retains its history across IP changes. Key attributes: MAC address (primary identifier), IP address (most recently observed), hostname, vendor, first-seen timestamp, last-seen timestamp, online status, consecutive-missed-scans count.
- **Annotation**: Human-assigned metadata for a device. Key attributes: role (one of: server, workstation, IoT, storage, networking, printer, dns, unknown), description (free text), tags (list of strings). One annotation per device.
- **Scan**: A record of one complete network scan pass. Key attributes: start time, end time, devices-found count, new-devices count.
- **Event**: A notable change detected by the system. Key attributes: event type (new-device, offline, back-online, scan-error), device reference (null for scan-error events), timestamp, details.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every device connected to 192.168.10.0/24 is discoverable within one scan cycle (15 minutes by default).
- **SC-002**: The device list page loads and displays all inventory data within 2 seconds.
- **SC-003**: A new device joining the network is logged as an event within one scan interval of its first appearance.
- **SC-004**: The admin can annotate a device (assign role + description) in under 30 seconds.
- **SC-005**: Pre-populated annotations for all 5 known Camelot devices are present after first-run discovery with no manual input required.
- **SC-006**: The event history log correctly categorizes new-device and offline events for 100% of logged events.
- **SC-007**: Device annotations and event history are retained without data loss across system restarts.

## Assumptions

- The advisor application scaffold (F4.1) is already deployed and running on HOLYGRAIL; this feature extends it.
- The advisor host (HOLYGRAIL, 192.168.10.129) has permission to send network probes on 192.168.10.0/24.
- MAC-to-vendor lookup uses a locally bundled prefix database to avoid dependency on external network availability.
- The 5 known Camelot devices (HOLYGRAIL .129, Torrentbox .141, NAS .105, Pi-hole .150, Mac .145) have stable IPs via DHCP reservation; these IPs seed the pre-populated annotations.
- Scan interval is a single global setting; per-device or per-subnet intervals are out of scope for this feature.
- Notifications (email, push, webhook) for new/offline device events are out of scope; events surface only within the dashboard and AI context.
- Mobile/responsive layout for the device list is a nice-to-have, not a requirement for this feature.
- The advisor dashboard requires no authentication; access is restricted to 192.168.10.0/24 at the network layer (Traefik/firewall). No login, session management, or user accounts are in scope.

## Clarifications

### Session 2026-04-09

- Q: Is authentication required to access the advisor dashboard? → A: No login required — access restricted to 192.168.10.0/24 at the network layer (Traefik/firewall)
- Q: What is the canonical identity key for a device? → A: MAC address — device history survives IP changes; IP address is recorded as most-recently-observed
- Q: How long should event history be retained? → A: 30 days
- Q: What should happen when a scheduled scan fails to complete? → A: Skip the cycle and log a scan-error event; do not update device statuses
- Q: Should a back-online event be logged when an offline device is detected again? → A: Yes — log a back-online event when device responds after being flagged offline
