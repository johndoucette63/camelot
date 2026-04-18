# Feature Specification: Home Assistant Integration

**Feature Branch**: `016-ha-integration`
**Created**: 2026-04-17
**Status**: Draft
**Input**: User description: "F6.1 Home Assistant Integration — Connect the Network Advisor to Home Assistant for IoT visibility, Thread network health, and bidirectional notifications. Source brief: `docs/F6.1-home-assistant-integration.md`."

## Clarifications

### Session 2026-04-17

- Q: Should Home Assistant-reported IoT devices merge into the advisor's unified device inventory, or live in a separate "Smart Home" surface? → A: Merge fully. Every Home Assistant device becomes (or updates) a row in the unified inventory, deduped against scanner-discovered rows by MAC/IP where possible. Thread/Zigbee devices without a LAN presence are still first-class inventory rows, tagged with their connectivity type. The inventory carries source provenance so an entry can be both scanner-seen and HA-known simultaneously.
- Q: What stable identifier should the advisor use as the primary key for HA-sourced devices with no LAN presence (Thread/Zigbee endpoints without MAC/IP)? → A: Home Assistant's per-device UUID (`device_id`). It is stable across HA restarts and entity renames, and it is the natural join key because HA groups all entities for one physical device under a single `device_id`. A rebuilt HA instance produces new `device_id`s and triggers a fresh reconciliation against the existing inventory.
- Q: How must the Home Assistant long-lived access token be protected at rest in the advisor? → A: Symmetric-encrypted in the advisor's database with the encryption key supplied via an environment variable on the advisor host. Matches the established repo pattern for secret material (PIA VPN credentials in 015-vpn-sidecar). Database dumps and backups remain safe as long as the env-var key is not checked in. Plaintext storage and env-var-only storage are both excluded.
- Q: What retry budget bounds notification-forwarding attempts to Home Assistant before the forwarder records a terminal failure? → A: Exponential backoff capped at 5 minutes total wall-clock (~4 attempts at roughly 30s, 60s, 120s, 240s). Covers a normal HA restart or reverse-proxy reload; stops before most HA OS upgrade windows so the advisor does not chase a multi-minute upgrade. On give-up the advisor records a terminal delivery failure on the alert and raises a recommendation that the alert was not delivered.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — See IoT device state in the advisor dashboard (Priority: P1)

As the Camelot admin, I want the advisor dashboard to surface the current state of the IoT devices Home Assistant already manages (online/offline, key sensor readings, automation availability) so that I can understand my home's IoT health without jumping between Home Assistant and the advisor.

**Why this priority**: This is the foundational integration. Everything else in this feature — Thread health, outbound notifications — depends on the advisor being able to authenticate with Home Assistant, pull entity state, and display it. Until this works, the rest of the feature cannot be demonstrated.

**Independent Test**: Can be fully tested by configuring the Home Assistant connection in the advisor (base URL + long-lived access token), opening the advisor dashboard, and confirming that a representative set of Home Assistant entities (e.g., a known online switch, a known offline sensor, a temperature reading) appears with state values consistent with what Home Assistant shows for the same entities. Toggling an entity in Home Assistant should produce an updated state in the advisor within one refresh cycle.

**Acceptance Scenarios**:

1. **Given** the admin has not yet configured a Home Assistant connection, **When** they visit the settings page, **Then** they see a Home Assistant configuration panel with fields for base URL and access token, and a "Test connection" control that confirms the credentials reach Home Assistant successfully.
2. **Given** a valid Home Assistant connection has been configured, **When** the next refresh cycle runs, **Then** the advisor retrieves the filtered set of Home Assistant entities and shows each entity's friendly name, domain, current state, and last-changed timestamp in the dashboard.
3. **Given** the advisor has a cached snapshot of Home Assistant state, **When** the user toggles an entity in Home Assistant, **Then** the advisor reflects the new state within one refresh cycle without requiring a manual page reload.
4. **Given** the Home Assistant connection is configured but currently unreachable, **When** the refresh cycle runs, **Then** the advisor keeps the last-known snapshot visible, marks it as stale with a visible timestamp, and records a recommendation that Home Assistant is degraded.
5. **Given** a configured access token has been revoked or expired, **When** the refresh cycle runs, **Then** the advisor stops updating the snapshot, surfaces an explicit "credential failure" state on the settings page, and raises a critical recommendation so the admin knows to rotate the token.

---

### User Story 2 — Diagnose Thread network health from the advisor (Priority: P2)

As the Camelot admin, I want the advisor to show me the state of every Thread border router and the Thread devices connected to them so that I can spot fragmentation, weak links, or failed border routers before IoT devices start dropping off.

**Why this priority**: Thread fragmentation is the single most common failure mode in this home's IoT stack (HomePods + Aqara hubs acting as border routers for a mixed device set). Surfacing it directly in the advisor is the concrete payoff of connecting to Home Assistant — turning raw IoT data into a diagnostic tool. It ships after Story 1 because it is a specialized view of the same data.

**Independent Test**: Can be fully tested by opening the advisor's Thread view and comparing the listed border routers, their online/offline status, and the device counts against what Home Assistant's Thread integration reports. Deliberately powering off one border router should cause the advisor to mark it offline within one refresh cycle and flag any orphaned devices.

**Acceptance Scenarios**:

1. **Given** the advisor is connected to Home Assistant and at least one Thread border router is active, **When** the admin opens the Thread view, **Then** they see every known border router listed with name, model, online state, and the number of Thread devices currently associated with it.
2. **Given** a border router goes offline, **When** the next refresh cycle runs, **Then** the advisor marks that border router offline, shows how many devices are orphaned or have switched parents, and raises a recommendation identifying the failed border router.
3. **Given** a Thread device has dropped off the network entirely, **When** the refresh cycle runs, **Then** the advisor shows the device as missing from the Thread topology and retains its last-known parent border router so the admin can reason about the failure path.
4. **Given** the admin asks the AI chat a Thread-related question (e.g., "why are my Aqara sensors dropping?"), **When** the chat pipeline responds, **Then** the answer incorporates the current Thread topology data (border-router health, device parentage, known fragmentation) retrieved through this integration.
5. **Given** Home Assistant's Thread integration exposes no data (e.g., only non-Thread entities are configured), **When** the admin opens the Thread view, **Then** the view renders an empty-state message explaining that no Thread data was found rather than failing or silently showing a blank panel.

---

### User Story 3 — Receive advisor alerts as Home Assistant push notifications (Priority: P2)

As the Camelot admin, I want critical advisor alerts delivered as notifications through Home Assistant so that I get a push notification on my phone via the existing Home Assistant companion app, without having to set up or maintain a second notification channel.

**Why this priority**: The advisor already has an alert system (from Feature 4.5 / 011-recommendations-alerts) but lacks a mobile-delivery path. Home Assistant is already installed on the admin's phone, so piggy-backing on its push pipeline is the shortest route to "I hear about a critical issue while away from the dashboard." It ships alongside Story 2 because it is independent of Thread work.

**Independent Test**: Can be fully tested by creating or triggering a critical-severity alert in the advisor, verifying the alert payload arrives at Home Assistant (visible in its notification history or the target service's logs), and confirming the push notification lands on the phone via the Home Assistant companion app.

**Acceptance Scenarios**:

1. **Given** the admin has configured Home Assistant as a notification sink in the advisor and selected a target Home Assistant notification service (e.g., `notify.mobile_app_<device>`), **When** a critical advisor alert fires, **Then** the advisor sends a notification request to Home Assistant containing the alert title, message, severity, and affected target within 30 seconds of the alert firing.
2. **Given** the Home Assistant notification sink is configured with a severity threshold of "critical only", **When** a warning-severity alert fires, **Then** no notification is sent to Home Assistant and the alert history still records the alert with a "not forwarded" marker.
3. **Given** the admin raises the forwarding threshold to include warnings, **When** a warning-severity alert fires, **Then** the advisor forwards that alert to Home Assistant using the same payload shape as critical alerts.
4. **Given** Home Assistant is unreachable at the moment an alert fires, **When** the forwarder attempts delivery, **Then** the alert is still recorded locally, the delivery failure is logged on the alert record, and the forwarder retries on a bounded schedule before giving up.
5. **Given** an alert is muted for its `(rule, target)` pair under the existing alert mute mechanism, **When** that rule re-fires, **Then** no Home Assistant notification is produced for the suppressed firing, consistent with the rest of the alert pipeline.

---

### Edge Cases

- Home Assistant base URL is reachable but returns an unexpected response shape (e.g., a reverse proxy serving a maintenance page). The advisor must distinguish "connection failed" from "authentication failed" from "unexpected payload" in the UI so the admin can fix the right thing.
- Access token is valid but lacks the scope needed to read some entity domains. The advisor should show exactly which entities it could not read rather than silently dropping them.
- Home Assistant entity IDs change (admin renames a device). The advisor must not assume entity IDs are stable identities; it should key its cache by entity ID but tolerate a vanishing-then-reappearing ID as a normal event, not as a device that has gone permanently missing.
- A Thread border router is mis-reported as "online" by Home Assistant while being functionally dead (e.g., radio hung). The advisor's role is to surface Home Assistant's view of reality; it does not independently validate border-router health.
- The advisor's alert forwarder fires during a Home Assistant upgrade window. The retry budget is bounded at 5 minutes; an upgrade that outlasts the budget produces a recommendation that the alert was recorded but not delivered, not a retry loop.
- Token rotation: the admin rotates the long-lived access token in Home Assistant. The advisor must surface the authentication failure within one refresh cycle so the admin knows to update the token in advisor settings.
- Alert storm: many alerts fire within a short window. The forwarder must not flood Home Assistant; it respects the existing dedup/mute logic and additionally coalesces burst traffic so a single incident produces one push, not fifty.

## Requirements *(mandatory)*

### Functional Requirements

#### Connection & Configuration

- **FR-001**: The advisor MUST allow an admin to configure a single Home Assistant connection consisting of a base URL and a long-lived access token.
- **FR-002**: The advisor MUST validate the configured connection on save using a live test against Home Assistant, reporting success, authentication failure, and network failure as distinct outcomes.
- **FR-003**: The advisor MUST store the Home Assistant access token symmetric-encrypted in its database, with the encryption key supplied via an environment variable on the advisor host. The token MUST NOT appear in logs, error messages, or any payload sent to the browser, and MUST NOT be committed to version control in any form (including migrations or seed data).
- **FR-004**: The advisor MUST allow the admin to update or delete the configured connection, and MUST stop polling Home Assistant immediately when the connection is deleted.

#### Entity State Ingestion

- **FR-005**: The advisor MUST poll Home Assistant on a configurable interval (default 60 seconds) and store a snapshot of the filtered entity set with their state, friendly name, domain, and last-changed timestamp.
- **FR-006**: The advisor MUST ingest only the curated set of entity domains relevant to infrastructure monitoring (network/connectivity, diagnostic sensors, Thread-related entities, binary sensors for online/offline) rather than the full entity universe, to keep the snapshot scoped to the advisor's purpose.
- **FR-007**: The advisor MUST expose the current Home Assistant snapshot in the dashboard with enough context (friendly name, domain, state, last-changed time, staleness indicator) for the admin to understand what each entity is without opening Home Assistant.
- **FR-008**: The advisor MUST persist the latest successful snapshot so that a temporary Home Assistant outage does not empty the dashboard; stale data MUST be visibly marked as such.
- **FR-009**: The advisor MUST make the Home Assistant snapshot available to the AI chat pipeline so that chat questions can be answered with current IoT context.

#### Thread Topology

- **FR-010**: The advisor MUST identify which ingested entities represent Thread border routers (by Home Assistant device class, integration source, or documented identification strategy) and present them as first-class objects in a Thread view.
- **FR-011**: The advisor MUST show, for each border router, its online state, model or identity, and the count of Thread devices currently parented to it.
- **FR-012**: The advisor MUST list Thread devices known to Home Assistant with their current parent border router (if reported) and their online state.
- **FR-013**: The advisor MUST render a clear empty state when Home Assistant exposes no Thread data, rather than a blank panel.
- **FR-014**: The advisor MUST raise a recommendation when a previously-online border router transitions to offline.

#### Notification Forwarding

- **FR-015**: The advisor MUST support Home Assistant as a notification sink within the existing alert system (established in Feature 4.5 / 011-recommendations-alerts).
- **FR-016**: Each Home Assistant notification sink configuration MUST name a specific Home Assistant notification service target (for example, a mobile-app notify service) so the admin controls where the push lands.
- **FR-017**: Each Home Assistant notification sink configuration MUST have a severity threshold (default: critical only) that governs which alerts are forwarded.
- **FR-018**: Outbound notifications MUST include, at minimum: alert title, human-readable message, severity, rule identity, affected target identity, and a timestamp.
- **FR-019**: A forwarded alert MUST be recorded on the alert itself with delivery status (sent, failed, suppressed, retrying) so the alert history remains honest about what reached the user.
- **FR-020**: Delivery failures MUST retry with exponential backoff capped at 5 minutes of total wall-clock time (approximately 30s, 60s, 120s, 240s). Retries MUST NOT block the advisor's own alert state transitions. On exhausting the retry budget, the advisor MUST record a terminal delivery failure on the alert and raise a recommendation that the alert was not delivered.
- **FR-021**: Muted `(rule, target)` pairs MUST NOT produce Home Assistant notifications, consistent with the existing mute semantics.
- **FR-022**: The advisor MUST deduplicate notifications so that a single alert instance produces at most one Home Assistant notification, even if multiple forwarding attempts occur.

#### Failure Modes & Observability

- **FR-023**: The advisor MUST treat Home Assistant unreachability as a degraded-but-operational state: it continues to serve its own dashboards, it raises a recommendation, and it resumes polling automatically once reachability returns.
- **FR-024**: The advisor MUST surface Home Assistant authentication failures explicitly in the settings page and as a critical recommendation so that a silently-expired token cannot go unnoticed.
- **FR-025**: Integration health (last successful poll timestamp and current error class, if any) MUST be visible in the existing service registry or dashboard health-status surface, not buried in logs.

#### Device Inventory Integration

- **FR-026**: Home Assistant-known devices MUST merge into the advisor's unified device inventory (established in 008-network-discovery-inventory and enriched by 013-device-enrichment). Each inventory row MUST carry a source marker indicating Home Assistant origin (in addition to, or instead of, scanner-discovered origin), and MUST store the Home Assistant `device_id` (HA's per-device UUID) as the stable identifier that links the inventory row back to Home Assistant.
- **FR-027**: When a Home Assistant device has a resolvable LAN presence (IP or MAC on the Camelot subnet), the advisor MUST dedupe it against any existing inventory row for that LAN device rather than creating a duplicate, so a single physical device has a single inventory entry with merged provenance from both sources. The HA `device_id` MUST be attached to the matched row as part of the merge.
- **FR-028**: Thread and other non-LAN Home Assistant devices (no IP on the Camelot subnet) MUST still be represented in the inventory as first-class rows keyed by the HA `device_id`, flagged with their connectivity type (Thread, Zigbee, etc.) so the admin sees the whole device population in one place.
- **FR-029**: When a Home Assistant connection is deleted or a device is removed from Home Assistant, the advisor MUST clear the Home Assistant provenance (including the stored `device_id`) on the affected inventory rows. Rows with no remaining source of truth (no scanner detection, no Home Assistant link) MUST be handled under the existing inventory-pipeline rules for stale devices rather than silently deleted here.
- **FR-030**: When the Home Assistant instance is rebuilt and emits new `device_id` values for the same physical devices, the advisor MUST treat the new identifiers as a fresh reconciliation: LAN-present devices re-match through IP/MAC, and non-LAN devices produce new inventory rows while the previously-linked rows fall through the standard stale-device flow (no attempt is made to guess a correspondence between old and new `device_id`s).

### Key Entities

- **Home Assistant Connection**: The single configured connection to the Home Assistant instance. Tracks base URL, the encrypted access token (symmetric-encrypted at rest with a key supplied via environment variable), last-successful-poll timestamp, current error (if any), and configuration metadata. There is at most one connection.
- **HA Entity Snapshot**: A point-in-time record of a single Home Assistant entity the advisor cares about. Includes entity ID, domain, friendly name, current state, last-changed timestamp, and a small set of attributes relevant to the advisor's views.
- **Thread Border Router**: A logical record derived from Home Assistant entities that represents a single border router. Tracks identity, model, online state, and associated device count.
- **Thread Device**: A logical record derived from Home Assistant entities that represents a Thread end-device. Tracks identity, parent border router (if reported), and online state.
- **Notification Sink — Home Assistant Variant**: A configuration row extending the existing notification-sink entity to describe "send to Home Assistant notification service X with severity threshold Y".
- **Outbound Notification Delivery**: A per-alert record of whether the advisor attempted to forward the alert to Home Assistant, the outcome (sent, failed, suppressed by mute, not forwarded due to threshold), and the timestamp of the last attempt.
- **Inventory Device (extended)**: The existing unified-inventory device row is extended with a Home Assistant provenance marker — the HA `device_id` as the canonical link back to Home Assistant, connectivity type for non-LAN devices such as Thread or Zigbee, and references to the HA Entity Snapshots belonging to that `device_id`. A device may carry both scanner-discovered provenance (MAC/IP) and Home Assistant provenance (`device_id`) simultaneously after deduplication.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After configuring a valid connection, the admin can see fresh Home Assistant entity state on the advisor dashboard within 60 seconds, without leaving the dashboard.
- **SC-002**: When a Thread border router goes offline, the advisor reflects the change and produces a recommendation within one poll cycle (default 60 seconds) of Home Assistant reporting the change.
- **SC-003**: When a critical advisor alert fires, the corresponding Home Assistant push notification arrives on the admin's phone within 30 seconds in at least 95% of trials, assuming Home Assistant and the companion app are functioning normally.
- **SC-004**: When Home Assistant is unreachable for up to 10 minutes, the advisor continues to render its own dashboards, preserves the last-known Home Assistant snapshot with a visible staleness marker, and automatically resumes polling on recovery without operator intervention.
- **SC-005**: When the admin rotates the Home Assistant access token, the advisor surfaces the authentication failure within 60 seconds and raises a critical recommendation so the admin is alerted to rotate the token in advisor settings.
- **SC-006**: The advisor can answer a Thread-diagnostics question through the AI chat using live Home Assistant data, without the admin pasting Home Assistant output into the chat manually.
- **SC-007**: During an alert storm of 10+ alerts firing in 60 seconds, the advisor forwards each distinct alert instance to Home Assistant at most once, producing no duplicate pushes for the same `(rule, target)` instance.
- **SC-008**: After Home Assistant ingestion runs, the unified device inventory shows a single row per physical device — a Home Assistant device that is also on the LAN produces no duplicates — and Thread/Zigbee devices appear in the inventory with their connectivity type clearly indicated.

## Assumptions

- Home Assistant is already installed and operational on a dedicated Raspberry Pi in the Camelot network; this feature integrates with that deployment rather than standing up a new one.
- A long-lived access token is the authentication mechanism, matching Home Assistant's standard practice. OAuth2 flow is out of scope for v1.
- Only one Home Assistant instance exists in the home; multi-instance support is out of scope.
- The advisor's existing alert system (lifecycle, dedup, mute, severity model, notification sinks) from Feature 4.5 (011-recommendations-alerts) is the canonical alert pipeline; this feature extends it rather than creating a parallel system.
- The Home Assistant companion app is already installed on the admin's phone and registered as a notification service in Home Assistant; this integration targets that pre-existing service rather than provisioning it.
- `INFRASTRUCTURE.md` will be updated as part of the implementation plan to capture the Home Assistant device (IP, OS version, Home Assistant version, key integrations, identified Thread border routers). The documentation update is a required side-effect of shipping this feature, not a standalone user story.
- Entity-domain filtering uses a curated built-in list in v1; an admin-managed allowlist UI is a plausible future enhancement but is out of scope here.
- Default severity threshold for Home Assistant forwarding is "critical only", with the admin able to broaden it per sink.
- Home Assistant alerts that originate inside Home Assistant (its own automations) remain Home Assistant's concern; this feature does not import Home Assistant notifications into the advisor's alert log.
- The advisor polls Home Assistant; Home Assistant does not push to the advisor via webhooks or WebSocket events in v1. Real-time streaming is a plausible future enhancement.

## Dependencies

- **F4.5 / 011-recommendations-alerts** — provides the alert lifecycle, severity model, mute semantics, and notification-sink abstraction this feature extends.
- **F4.1 / 008-network-discovery-inventory** and **013-device-enrichment** — relevant because scope question FR-026 turns on whether HA-sourced devices merge into the unified inventory built by these features.
- **010-ai-advisor-chat** — the AI chat pipeline is the surface that answers Thread-diagnostic questions using the snapshot produced here.
- Operational dependency on the Home Assistant deployment itself (hardware, OS, Home Assistant version, Thread integrations) remaining healthy and reachable from the advisor host.
