# Feature Specification: Recommendations & Alerts

**Feature Branch**: `011-recommendations-alerts`
**Created**: 2026-04-10
**Status**: Draft
**Input**: User description: "F4.5 Recommendations and Alerts — Rule-based recommendation engine and configurable alert system with dashboard log. Proactively surfaces actionable advice (rule-based plus LLM-assisted), supports configurable thresholds, displays an alert history log, and optionally forwards critical alerts to Home Assistant."

## Clarifications

### Session 2026-04-10

- Q: Alert lifecycle — what are the states and transitions? → A: Distinct `active → acknowledged → resolved` states. Acknowledgement is user-driven and does not clear the underlying condition; resolution is condition-driven (auto) or user-driven (manual override). If a resolved condition re-fires, a new instance is created rather than re-opening the old one.
- Q: How should the engine deduplicate alert instances? → A: Deduplicate by `(rule_id, target_id)` where `target_id` is the device or service the rule evaluated. At most one non-resolved instance may exist per (rule, target) pair; a new instance is only created after the prior one reaches `resolved`.
- Q: How is severity assigned to an alert? → A: Each rule has a single fixed severity baked into its definition. The engine does not dynamically escalate severity based on metric magnitude or age; severity is determined by the rule, not by runtime state.
- Q: How does the admin suppress noise without changing global thresholds? → A: Per `(rule_id, target_id)` mute with a required TTL. The admin can mute a specific rule on a specific device for N hours; the mute auto-expires. While muted, re-firings of that (rule, target) pair do not produce active alerts but are still recorded in the log with a `suppressed` marker so the history stays honest.
- Q: What are the default sustained-breach window and post-resolution cool-down? → A: Sustained breach = 5 minutes (a metric-threshold rule only fires once the condition has held for the most recent 5 minutes). Cool-down = 10 minutes (after a `(rule, target)` instance reaches `resolved`, a new instance for the same pair cannot be created until 10 minutes have elapsed). Both values are global defaults; per-rule overrides are out of scope for v1.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Proactive rule-based recommendations (Priority: P1)

As the Camelot admin, I want the advisor to proactively tell me about problems and optimizations across my home infrastructure so that I can catch issues before they turn into outages or service degradation.

**Why this priority**: This is the core value of the feature — turning raw telemetry into actionable advice. Without it, the admin still has to read dashboards manually and correlate metrics themselves. A rule-based engine is the reliable foundation that must work even if the LLM is unavailable, so it ships first.

**Independent Test**: Can be fully tested by deliberately driving a device into a condition that trips a rule (e.g., generating sustained CPU load on a Pi or filling a disk past the threshold), then verifying that a matching recommendation appears in the dashboard within one refresh cycle. No other user story needs to be implemented for this to deliver value.

**Acceptance Scenarios**:

1. **Given** a Pi's CPU has been above 80% for a sustained window of at least 5 minutes, **When** the next evaluation cycle runs, **Then** a recommendation appears suggesting the workload be migrated to HOLYGRAIL.
2. **Given** a device reports disk usage above 85%, **When** the next evaluation cycle runs, **Then** a storage warning recommendation appears naming the affected device and mount point.
3. **Given** a tracked service has been marked down for longer than five minutes, **When** the next evaluation cycle runs, **Then** an investigation recommendation is raised for that service.
4. **Given** Ollama is unreachable, **When** the next evaluation cycle runs, **Then** a recommendation notifies the admin that AI-assisted features are degraded.
5. **Given** a device appears on the network that is not in the inventory, **When** the next evaluation cycle runs, **Then** a security recommendation flags the unknown device with its IP and MAC.
6. **Given** a tracked device has failed to report metrics for more than the device-offline threshold, **When** the next evaluation cycle runs, **Then** a device-offline recommendation is raised for that device (distinct from any metric-threshold alerts it may have produced earlier).
7. **Given** multiple recommendations already exist for the same underlying condition, **When** the engine re-evaluates, **Then** duplicate recommendations are not created for the same unresolved condition.

---

### User Story 2 - Configurable alert thresholds (Priority: P2)

As the Camelot admin, I want to set custom thresholds for the alerts the advisor raises so that alerts match my tolerance levels and the system does not flood me with noise.

**Why this priority**: Rule-based recommendations ship first with sensible defaults, but every home has different tolerances — a Pi running as a torrent box is expected to sit at higher CPU than a DNS node. Without configurable thresholds, the admin will either disable alerts or learn to ignore them, which defeats the purpose. This is the necessary follow-on to make Story 1 usable day-to-day.

**Independent Test**: Can be fully tested by opening the settings page, changing a threshold (e.g., lowering the CPU threshold below current usage), saving, and verifying that on the next evaluation cycle the corresponding recommendation fires even though usage has not changed. Reverting the threshold should stop the recommendation from firing on the following cycle.

**Acceptance Scenarios**:

1. **Given** the admin navigates to the settings page, **When** the page loads, **Then** the current thresholds for every metric consumed by the rule catalog (CPU percent, disk percent, service-down duration, device-offline duration) are shown with their default values pre-populated if never changed.
2. **Given** the admin changes a threshold value and saves, **When** the save completes, **Then** the new value is persisted and displayed on subsequent visits to the settings page.
3. **Given** a threshold has been updated, **When** the next evaluation cycle runs, **Then** the engine uses the new threshold without requiring a restart.
4. **Given** the admin enters an out-of-range or invalid threshold (e.g., negative number, above 100% for a percentage field), **When** they attempt to save, **Then** the system rejects the change with an explanatory error and keeps the prior value.

---

### User Story 3 - Searchable alert and recommendation history (Priority: P2)

As the Camelot admin, I want a searchable log of all past alerts and recommendations so that I can review what happened, when, and whether I already addressed it.

**Why this priority**: Recommendations that only live in the current dashboard view lose their value the moment they scroll off-screen or resolve. A history log turns the feature into a record of incidents the admin can audit after the fact. This is critical for the "catch issues before outages" promise but can ship alongside or just after thresholds.

**Independent Test**: Can be fully tested by generating a known sequence of alerts (e.g., trip CPU, resolve it, trip disk), navigating to the alert history page, and verifying each entry appears with correct timestamp, severity, device, and message. Filters can be validated by narrowing to one severity or date range and confirming only matching entries remain.

**Acceptance Scenarios**:

1. **Given** one or more past alerts exist, **When** the admin opens the alert log page, **Then** each entry shows timestamp, severity, affected device or service, and the alert message.
2. **Given** the admin selects a severity filter, **When** the filter is applied, **Then** only alerts matching that severity (info, warning, or critical) are shown.
3. **Given** the admin filters by device and date range, **When** the filter is applied, **Then** only alerts for that device within that window are shown.
4. **Given** the admin marks an alert as acknowledged or resolved, **When** the status is saved, **Then** that state persists across page reloads and is visible in the log.
5. **Given** an alert was recorded more than 30 days ago, **When** the log is queried, **Then** the alert may no longer appear (retention window has elapsed) but anything within 30 days is still present.

---

### User Story 4 - AI-assisted alert summarization and explanation (Priority: P3)

As the Camelot admin, I want related alerts consolidated into a single narrative and anomalies explained in context so that I can understand root causes instead of parsing a wall of individual threshold notifications.

**Why this priority**: This is additive polish on top of rule-based alerts. It makes the system dramatically more pleasant to use when working correctly, but the underlying admin workflow must still work when Ollama is unavailable. Shipping after P1 and P2 lets the core system stabilize first.

**Independent Test**: Can be fully tested by triggering two or more simultaneous related alerts (e.g., CPU and disk I/O on Torrentbox at the same time Sonarr/Radarr imports are running) and verifying that the dashboard shows a consolidated narrative referencing both metrics and a plausible correlating cause, in addition to the individual rule-based alerts. Stopping Ollama and re-running the scenario should still show the individual rule-based alerts with the narrative gracefully omitted.

**Acceptance Scenarios**:

1. **Given** multiple rule-based alerts fire in the same evaluation cycle for correlated metrics, **When** the AI layer runs, **Then** a single consolidated narrative is displayed summarizing them alongside the individual alerts.
2. **Given** a metric has deviated from its normal pattern, **When** the AI layer runs, **Then** the narrative includes a plausible explanation that references other data sources (e.g., scheduled scans, known service activity).
3. **Given** Ollama is unreachable or slow, **When** the evaluation cycle completes, **Then** rule-based alerts still display normally and the absence of AI narrative does not block or break the dashboard.
4. **Given** the AI layer generates a contextual recommendation (e.g., suggesting a workload move based on device roles), **When** the recommendation is displayed, **Then** it is clearly marked as AI-assisted so the admin can distinguish it from deterministic rule output.

---

### User Story 5 - Critical alerts forwarded to Home Assistant (Priority: P3)

As the Camelot admin, I want critical alerts forwarded to Home Assistant as notifications so that I get alerted on my phone even when I am not looking at the dashboard.

**Why this priority**: Out-of-band notification is valuable but optional — the admin already gets alerts when they open the dashboard. This story is explicitly called out as optional in the source spec and depends on a separate Home Assistant integration existing. Shipping last avoids blocking the core feature on an external dependency.

**Independent Test**: Can be fully tested by enabling the integration in settings, configuring a webhook or endpoint, triggering a critical-severity alert, and verifying the expected notification arrives in Home Assistant with the alert message, device, and timestamp. Disabling the integration should stop further notifications without any restart.

**Acceptance Scenarios**:

1. **Given** the admin enables the Home Assistant integration and provides a valid endpoint, **When** a critical-severity alert is raised, **Then** a notification is sent to Home Assistant containing the alert message, affected device, and timestamp.
2. **Given** the integration is disabled, **When** any alert is raised, **Then** no notification is sent to Home Assistant.
3. **Given** the integration is enabled, **When** a non-critical (info or warning) alert is raised and the admin has not opted in to non-critical forwarding, **Then** no notification is sent.
4. **Given** the Home Assistant endpoint is unreachable, **When** an alert is raised, **Then** the alert is still recorded locally and the failure is logged without crashing the advisor.
5. **Given** the admin toggles the integration on or off, **When** the change is saved, **Then** the new state takes effect on the next alert without restarting the advisor.

---

### Edge Cases

- **Flapping alerts**: A metric that repeatedly crosses and un-crosses a threshold within a short window must not generate a new recommendation on every cycle. Flapping is controlled by the 5-minute sustained-breach requirement (FR-006a) and the 10-minute post-resolution cool-down (FR-006b).
- **Evaluation during device offline**: When a device is unreachable, metrics are absent rather than bad. The engine must distinguish "no data" from "bad data" and raise a device-down alert rather than spurious metric alerts.
- **Clock skew or missing timestamps**: If a data source reports a timestamp outside the expected window, the alert should still be recorded with the advisor's ingestion time and the anomaly noted.
- **Threshold set to a value the system cannot reach**: If the admin sets an impossible threshold (e.g., 200% CPU), the system must validate and reject rather than silently never fire.
- **Unknown-device false positives**: A device that appears briefly (e.g., guest phone) should be distinguishable from a device that persists. Only persistent unknown devices should escalate to a recommendation; or the admin should be able to dismiss a one-off.
- **Resolved conditions**: When the condition that triggered a recommendation clears, the recommendation should auto-resolve in the log rather than require manual dismissal, while preserving the historical record.
- **Storage growth of the alert log**: The 30-day retention window must be actively enforced; unbounded log growth should not be possible.
- **LLM hallucinated correlations**: AI-assisted narratives must not invent alerts that have no underlying rule-based evidence. The narrative layer should only consolidate or explain existing alerts.
- **Home Assistant webhook leaking secrets**: The webhook URL may contain a token; it must be stored securely and not echoed back to the UI in plaintext after save.

## Requirements *(mandatory)*

### Functional Requirements

#### Recommendation engine (core)

- **FR-001**: The system MUST evaluate a defined set of recommendation rules on every data refresh cycle.
- **FR-002**: The system MUST ship with at least six rule-based recommendations covering: sustained high Pi CPU, high disk usage, service-down duration, device offline (missing metrics), Ollama unavailability, and unknown devices on the network. Each rule MUST declare a fixed severity (`info`, `warning`, or `critical`) as part of its definition; severity MUST NOT vary at runtime based on metric magnitude or alert age.
- **FR-003**: The system MUST display current active recommendations in a dashboard panel visible on the main advisor view.
- **FR-004**: The system MUST deduplicate recommendations by `(rule_id, target_id)`, where `target_id` identifies the device or service the rule evaluated. At most one non-resolved instance MUST exist per (rule, target) pair at any time; a new instance MUST only be created once the prior one has reached `resolved`.
- **FR-005**: The system MUST track each alert instance through `active → acknowledged → resolved` states. It MUST auto-transition an instance to `resolved` when the underlying condition is no longer met, and it MUST allow the admin to manually resolve an instance. If a resolved condition re-fires in a later evaluation cycle, a new instance MUST be created rather than re-opening the prior one.
- **FR-006**: The system MUST distinguish missing-data conditions (device offline) from metric-threshold conditions and raise appropriate alerts for each.
- **FR-006a**: Metric-threshold rules MUST only fire once the underlying condition has held continuously for a sustained window of at least 5 minutes (global default). Brief spikes shorter than the window MUST NOT produce alerts.
- **FR-006b**: After a `(rule_id, target_id)` instance reaches `resolved`, the engine MUST enforce a cool-down period of at least 10 minutes (global default) during which no new instance for that pair may be created, even if the condition briefly re-trips.

#### Alert thresholds

- **FR-007**: The system MUST provide default thresholds for every metric consumed by the shipped rule catalog: CPU percent, disk percent, service-down duration, and device-offline duration. Unused or decorative thresholds MUST NOT be exposed in the settings UI.
- **FR-008**: Users MUST be able to edit thresholds via a dashboard settings page.
- **FR-009**: The system MUST persist user-configured thresholds to durable storage so that they survive restarts.
- **FR-010**: The system MUST validate threshold values on save and reject invalid inputs with an explanatory error.
- **FR-011**: The system MUST apply updated thresholds on the next evaluation cycle without requiring a service restart.
- **FR-011a**: Users MUST be able to mute a specific `(rule_id, target_id)` pair for a required TTL (e.g., "mute high-CPU on Pi-2 for 4 hours"). Mutes MUST auto-expire when the TTL elapses and MUST NOT require a service restart to take effect.
- **FR-011b**: While a `(rule_id, target_id)` pair is muted, the engine MUST NOT create new `active` instances for it. Re-firings during the mute window MUST still be recorded in the alert log with a `suppressed` marker so the audit trail is preserved.
- **FR-011c**: The system MUST display currently active mutes in the settings UI with their remaining TTL and MUST allow the admin to cancel a mute early.

#### Alert history log

- **FR-012**: The system MUST record every alert and recommendation that fires, including timestamp, severity, affected device or service, and the message shown to the admin.
- **FR-013**: The system MUST provide a log view filterable by severity (info, warning, critical), by device, and by date range.
- **FR-014**: Users MUST be able to acknowledge an active alert (without clearing the underlying condition) and to manually resolve it. Both state transitions MUST persist and be visible in the log.
- **FR-015**: The system MUST retain the alert log for a minimum of 30 days and MUST actively prune entries older than the retention window.
- **FR-016**: The system MUST expose the log through the dashboard UI with at-a-glance counts by severity.

#### AI-assisted layer

- **FR-017**: The system MUST optionally consolidate multiple simultaneous rule-based alerts into a single narrative using the local LLM service.
- **FR-018**: The system MUST optionally provide contextual explanations for metric deviations by correlating across available data sources.
- **FR-019**: The system MUST clearly distinguish AI-generated recommendations and narratives from deterministic rule output in the UI.
- **FR-020**: The system MUST degrade gracefully when the LLM service is unavailable — rule-based alerts and recommendations MUST continue to function and display normally.
- **FR-021**: AI-generated narratives MUST NOT fabricate alerts without an underlying rule-based trigger; they may only summarize, explain, or elaborate on existing alerts.

#### Home Assistant integration (optional)

- **FR-022**: The system MUST support an optional integration that forwards alerts to a configurable Home Assistant endpoint.
- **FR-023**: By default only critical-severity alerts MUST be forwarded; the severity cutoff MUST be configurable.
- **FR-024**: Forwarded notifications MUST include the alert message, affected device, and timestamp.
- **FR-025**: Users MUST be able to enable or disable the integration at runtime without restarting the advisor.
- **FR-026**: The system MUST record alerts locally even when the Home Assistant endpoint is unreachable, and MUST log the delivery failure without interrupting the evaluation cycle.
- **FR-027**: Integration credentials (e.g., webhook tokens) MUST be stored securely and MUST NOT be displayed in plaintext after save.

#### Shared with AI chat

- **FR-028**: Active alerts and recommendations MUST be available as context to the AI advisor chat feature so that the admin can ask questions about them.

### Key Entities *(include if feature involves data)*

- **Recommendation Rule**: A named rule that defines a condition over one or more metrics and produces a recommendation when the condition is met. Attributes include identifier, human-readable name, fixed severity (`info`, `warning`, or `critical`), condition description, and associated remediation advice. Rules are static and versioned with the advisor code; severity is a property of the rule definition and is not runtime-computed.
- **Threshold Setting**: A user-configurable numeric value associated with a metric (CPU, memory, disk, ping latency) that parameterizes one or more rules. Attributes include metric name, value, unit, default, and last-modified timestamp.
- **Alert / Recommendation Instance**: A concrete occurrence of a rule firing. Attributes include identifier, rule reference, target identifier (device or service the rule evaluated), severity, message, created timestamp, state (`active`, `acknowledged`, or `resolved`), acknowledged-at timestamp (nullable), resolved-at timestamp (nullable), resolution source (`auto` when the condition cleared, `manual` when the admin resolved it, null while active/acknowledged), and source (rule-based vs. AI-assisted). Uniqueness of the non-resolved state is enforced per `(rule_id, target_id)`; a new instance is created each time a rule re-fires after resolution.
- **AI Narrative**: A consolidated or explanatory piece of text produced by the LLM that references one or more alert instances. Attributes include body text, referenced alert identifiers, created timestamp, and a marker indicating AI origin.
- **Notification Sink Configuration**: Settings for outbound notification targets (currently Home Assistant). Attributes include target identifier, endpoint, credentials (stored securely), enabled flag, and minimum severity cutoff.
- **Unknown Device Observation**: A record of a device seen on the network that is not in the inventory, used to distinguish transient guests from persistent unknowns. Attributes include MAC, first-seen, last-seen, and dismissed flag.
- **Rule Mute**: A time-bounded suppression of a `(rule_id, target_id)` pair. Attributes include rule reference, target identifier, created-at timestamp, expires-at timestamp, and optional note. Mutes auto-expire and can be cancelled early. While a mute is active, matching rule firings are recorded in the log as `suppressed` but do not create active alert instances.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The admin receives a recommendation within one evaluation cycle after a rule's condition is met in at least 95% of test cases across all five core rules.
- **SC-002**: At least five rule-based recommendations ship on day one, each with a documented trigger condition and remediation message.
- **SC-003**: The admin can change any alert threshold from the settings UI and see the new value take effect within one evaluation cycle, with zero service restarts required.
- **SC-004**: The alert history log retains every recorded alert for at least 30 days and prunes older entries automatically, with log storage bounded even under sustained alert volume.
- **SC-005**: Filtering the alert log by severity, device, or date range returns the correct matching subset in under two seconds for typical home-scale volumes (thousands of entries).
- **SC-006**: When the LLM service is unavailable, the rule-based recommendation and alert flow continues to function with no user-visible errors and no lost alerts.
- **SC-007**: When enabled, Home Assistant receives critical alerts within 30 seconds of the rule firing in at least 95% of cases; delivery failures never prevent the alert from being recorded locally.
- **SC-008**: The admin reports a measurable reduction in time spent manually scanning dashboards to identify problems, as validated by self-assessment after one week of use.
- **SC-009**: Duplicate recommendations for the same unresolved condition occur in zero cases across a continuous 24-hour evaluation run under steady-state load.

## Assumptions

- Metrics for CPU, memory, disk, ping latency, service up/down, and network device presence are already available from earlier phases (device inventory, service registry, monitoring stack) and do not need to be collected by this feature.
- The advisor already has a durable database available for persisting thresholds, alert history, and configuration — this feature extends the existing schema rather than introducing new storage infrastructure.
- The advisor dashboard already has a settings area and a main view where a new recommendations panel and settings page can be added.
- The local LLM service (Ollama on HOLYGRAIL) is the target AI backend for summarization and explanation; no cloud LLM is in scope.
- "Evaluation cycle" aligns with the advisor's existing data refresh cadence; this feature does not introduce a separate scheduling system.
- Default thresholds will be chosen to match reasonable home-lab tolerances (e.g., CPU 80% over a 5-minute sustained window, disk 85%, service-down 5 minutes) and documented in the settings UI so admins know what they are changing from. The global sustained-breach window defaults to 5 minutes and the post-resolution cool-down defaults to 10 minutes; per-rule overrides are out of scope for v1.
- The Home Assistant integration is optional and not required for the feature to be considered complete — the advisor ships useful without it.
- 30-day retention is a minimum; longer retention is acceptable if storage allows, but anything above 30 days is not a requirement.
- The unknown-device rule depends on the network inventory feature (F4.2 / 008-network-discovery-inventory) being deployed and providing a reliable list of known devices.
- Notifications are one-way from the advisor to Home Assistant — there is no bidirectional acknowledgement flow in this feature.
