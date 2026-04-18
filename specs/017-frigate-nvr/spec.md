# Feature Specification: Frigate NVR — Local AI Camera Surveillance

**Feature Branch**: `017-frigate-nvr`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "@docs/F6.2-frigate-nvr.md"

## Clarifications

### Session 2026-04-18

- Q: How should the admin be alerted before `/mnt/frigate` fills, so retention is not bypassed by overflow? → A: Via a Camelot Advisor rule + threshold on the `/mnt/frigate` mount; alerts flow through the existing Advisor → HA notification-sink path.
- Q: Where should the MQTT broker live? → A: Mosquitto as a new container on HOLYGRAIL, inside the Frigate docker-compose stack (keeps the NVR stack self-contained and independent of HA-host reboots).
- Q: What does privacy mode pause? → A: Recording + detection only; the restreamer keeps running and the live view stays available to LAN clients (including the native HA Reolink integration). Rationale: stopping the restreamer would re-trigger the Reolink multi-connection bug on resume.
- Q: How are HA notifications delivered (attached media vs links)? → A: Snapshot image attached inline; full clip available via a clickable link into the Frigate UI (LAN-only). Keeps remote-access decisions deferred per the stated Phase 1 scope.
- Q: What should happen when GPU contention pushes detection latency past the SLO? → A: Add an Advisor rule that alerts on sustained detection-latency breach (e.g. P95 > 2s over 5 minutes); detector stays on GPU (observability only, no automatic CPU/Coral failover in Phase 1).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Live doorbell view with reliable event recording (Priority: P1)

A Camelot admin deploys a local NVR stack on HOLYGRAIL that pulls the Reolink Video Doorbell WiFi stream through a single upstream connection, records 24/7 footage to a dedicated drive, and saves clips when motion occurs — all without ever crashing the doorbell firmware.

**Why this priority**: This is the foundational surveillance slice. Without a stable camera feed and recordings, no other capability matters. The system must also respect the Reolink multi-connection firmware bug from day one, because the existing native Home Assistant Reolink integration will continue to consume the same doorbell.

**Independent Test**: Ring the doorbell ten times over ten minutes while the native HA Reolink integration is also active. Confirm the live stream stays connected in the NVR web UI, the doorbell never reboots or drops, continuous recording is written to disk for the full window, and at least one motion clip per ring is retrievable.

**Acceptance Scenarios**:

1. **Given** the NVR stack is deployed and the doorbell has a static DHCP reservation on the router, **When** HOLYGRAIL is rebooted, **Then** the stack comes back up automatically and the doorbell live stream is viewable in the NVR web UI within 2 minutes of boot.
2. **Given** both the NVR stack and the native Reolink HA integration are consuming the doorbell simultaneously through the restreamer, **When** the doorbell receives repeated presses, **Then** no connection drops, firmware crashes, or frame loss is observed in the restreamer health UI.
3. **Given** 24/7 continuous recording is enabled, **When** an admin reviews footage 5 days after an event, **Then** the continuous footage for that moment is still available on disk within the configured retention window.
4. **Given** the doorbell password contains only Reolink-safe characters, **When** the restreamer authenticates to the camera's RTSP endpoint, **Then** authentication succeeds and the stream is pulled cleanly with no silent encoding errors.

---

### User Story 2 - GPU-accelerated AI detection on the doorbell feed (Priority: P1)

Object detection runs on the RTX 2070 Super over the doorbell's sub-stream, classifying people, vehicles, packages, dogs, and cats in near-real-time, so that only meaningful events generate clips and HA signals (not every leaf blowing past the lens).

**Why this priority**: The entire "smart NVR" value proposition — and everything P2 builds on — depends on usable detections. Without GPU acceleration the CPU will be overloaded on a multi-camera Phase 2 expansion, and detection latency determines whether notifications feel responsive.

**Independent Test**: Walk into the frame, place a package on the porch, let a delivery vehicle pass, and walk a dog past. Within seconds each should appear as a correctly labeled event in the NVR event feed. Running `nvidia-smi` during the test must show the NVR process on the GPU, and CPU detection load must remain negligible.

**Acceptance Scenarios**:

1. **Given** the GPU detector is configured with a pinned model version and the sub-stream is assigned for detection, **When** a person enters the doorbell field of view, **Then** a `person` event appears in the NVR event feed within 1 second of motion starting.
2. **Given** Ollama is actively serving an LLM request on the same GPU, **When** the doorbell sees motion, **Then** detection still completes and an event is recorded (possibly with slightly higher latency) without the detector process crashing or falling back to CPU silently.
3. **Given** the tracked object list is `person`, `car`, `dog`, `cat`, `package`, **When** an untracked object (e.g. a shopping cart) moves through the frame, **Then** no event clip is generated and no notification is emitted.

---

### User Story 3 - Wife-friendly event review in the web UI (Priority: P1)

A non-technical household member opens the NVR web UI on their phone or laptop, sees a Nest-like dashboard of recent activity thumbnails, scrolls a vertical timeline through past events, and filters by date, camera, or object type — all without guidance or training.

**Why this priority**: The feature spec explicitly identifies this UX as a release gate: "acceptance-testable and gates release". The technical pipeline is worthless if the household cannot actually use it to review who came to the door.

**Independent Test**: A household member who has never seen the system before is given the URL and asked, unprompted: (a) "What's happened in the last 24 hours?" (b) "Show me everything from yesterday afternoon." (c) "Was there a package delivery this week?" They must complete all three without being shown how, within 3 minutes total.

**Acceptance Scenarios**:

1. **Given** the NVR has been running for at least 48 hours with events recorded, **When** a household member opens the web UI on the local network, **Then** the landing dashboard shows a glanceable grid of the most recent event thumbnails without requiring login navigation.
2. **Given** multiple events from different days exist, **When** the user scrolls the vertical timeline, **Then** events are grouped by day with clear timestamps and thumbnails, and tapping a thumbnail plays the clip inline.
3. **Given** the filter controls are visible, **When** the user filters by date range AND object type (e.g. "yesterday, packages only"), **Then** only matching events are shown and the filter state is obvious in the UI.

---

### User Story 4 - Home Assistant integration with rich notifications (Priority: P2)

Detections flow from the NVR into Home Assistant via MQTT, exposing per-camera sensors for visitor, person, and package. Automations fire on doorbell press, person detection, and package delivery. A privacy-mode switch in HA pauses recording and detection when desired.

**Why this priority**: The surveillance system must integrate with the household's existing HA-driven automations (porch lights, phone notifications) to deliver its full value. This builds on the stable detection pipeline from US1+US2 and cannot be completed without them, but the NVR is independently useful even if HA integration is deferred by a week.

**Independent Test**: Press the doorbell, walk up to the porch, and leave a package in view. Within seconds, a phone notification with snapshot and live-stream link arrives, porch lights turn on, and a separate notification with the package clip link follows. Toggling the privacy switch in HA immediately halts all three behaviors.

**Acceptance Scenarios**:

1. **Given** the MQTT broker is running and reachable and the Frigate HA integration is installed via HACS, **When** a person is detected at the front door, **Then** porch lights turn on within 3 seconds via HA automation.
2. **Given** the doorbell button is pressed, **When** the event propagates through the NVR to HA, **Then** a rich push notification with snapshot and live-stream link arrives on the admin's phone within 5 seconds.
3. **Given** a package is detected, **When** the event closes (object leaves or settles), **Then** HA delivers a notification with the event clip attached or linked.
4. **Given** the privacy-mode switch in HA is toggled on, **When** motion occurs, **Then** no recording is written and no detection events are emitted until the switch is toggled off.

---

### User Story 5 - Phase 2 expansion without restructuring (Priority: P3)

The stack and config are structured so that adding the future Reolink Home Hub and solar cameras is an incremental config change, not a rewrite. A self-service checklist documents the exact steps.

**Why this priority**: Phase 2 is deferred hardware. Getting the structure right now costs a few hours; getting it wrong means a painful rewrite in 6 months. But it does not block any Phase 1 value, hence P3.

**Independent Test**: A future admin (or future self, 6 months later) picks up only the checklist file — without re-reading this spec or the source feature doc — and successfully onboards a hypothetical second camera to the stack end-to-end.

**Acceptance Scenarios**:

1. **Given** the deployment is complete, **When** an admin opens the deployment configs, **Then** commented stubs for Phase 2 cameras behind the Home Hub are present and clearly labeled.
2. **Given** the Phase 2 expansion checklist in `docs/`, **When** a future admin follows it to onboard a new solar camera, **Then** the full end-to-end process is self-contained and requires no re-reading of this spec or the F6.2 source doc.
3. **Given** the documented RTSP/restreamer conventions for hub-backed cameras, **When** a new camera is added, **Then** the admin knows exactly which URL pattern to use without trial-and-error against the Home Hub firmware.

---

### Edge Cases

- **Doorbell offline**: Camera loses power or Wi-Fi. The NVR must not crash-loop; the web UI must show the camera as offline; recovery must be automatic when the doorbell returns.
- **Storage full**: `/mnt/frigate` approaches capacity faster than retention caps prune. The system must enforce retention before disk fills, and the admin must be alerted before footage is lost to overflow rather than retention policy.
- **GPU contention peak**: Both Ollama and the NVR hit the GPU simultaneously during peak use. Detection latency may degrade but the NVR must not crash; if detection consistently exceeds acceptable latency, this must be visible in logs for diagnosis.
- **MQTT broker unreachable**: HA automations cannot fire. The NVR itself must continue to record and run detection; MQTT reconnection must be automatic.
- **HA integration offline**: The native HA Reolink integration is disabled or the HA host is rebooting. The NVR must continue to serve the doorbell feed to its own clients through the restreamer regardless of HA state.
- **Stack restart during recording**: A reboot or container restart happens mid-event. No footage corruption; recording resumes on restart.
- **Malformed camera password**: Special characters outside the Reolink-safe set are used during setup. This must be caught during onboarding (documented constraint) rather than manifesting as a silent stream failure days later.
- **Phase 2 RTSP divergence**: Cameras behind the Home Hub use different URL patterns than the wired doorbell. The config structure must not embed assumptions that break when Phase 2 cameras are added.

## Requirements *(mandatory)*

### Functional Requirements

#### Infrastructure & deployment

- **FR-001**: The NVR stack MUST be deployed as a set of containers on HOLYGRAIL, alongside the existing Ollama stack, with all image tags pinned to specific versions.
- **FR-002**: A restreamer component MUST sit between each camera and all consumers (the NVR, the native Home Assistant Reolink integration, and any other clients) such that no camera is connected to directly by more than one upstream process.
- **FR-003**: The NVIDIA Container Toolkit MUST be configured so the NVR container has GPU access shared with Ollama on the same host.
- **FR-004**: NVR configuration MUST be persisted on disk under a stable path (`/opt/frigate/config`) so it survives container recreation.
- **FR-005**: Footage (continuous + event clips) MUST be stored on a dedicated drive or partition mounted at `/mnt/frigate`, separate from the OS and other service volumes.
- **FR-006**: The stack MUST come up automatically and cleanly on a HOLYGRAIL reboot without manual intervention.

#### Camera onboarding

- **FR-007**: The Reolink Video Doorbell WiFi MUST have a static DHCP reservation on the router (not an on-device static IP).
- **FR-008**: RTSP and ONVIF MUST be enabled on the doorbell via the Reolink app before onboarding.
- **FR-009**: The doorbell password MUST use only the Reolink-safe character set (`a-z A-Z 0-9 @$*~_-+=!?.,:;'()[]`). Any other characters are prohibited to avoid silent RTSP encoding failures.
- **FR-010**: The restreamer MUST be the single consumer of the doorbell's RTSP endpoint; the NVR and the native Home Assistant Reolink integration MUST both consume from the restreamer, never from the camera directly.

#### Detection & recording

- **FR-011**: Object detection MUST run on the RTX 2070 Super via GPU acceleration as the primary detector.
- **FR-012**: The detection model MUST be a specific, pinned version of YOLOv8 or YOLOv9 recorded in the NVR config.
- **FR-013**: Detection MUST operate on the doorbell's sub-stream (low resolution); recording MUST use the main stream.
- **FR-014**: Tracked object classes MUST be exactly: `person`, `car`, `dog`, `cat`, `package`.
- **FR-015**: Detection latency on the doorbell feed MUST be sub-second under normal (non-contention) conditions.
- **FR-016**: 24/7 continuous recording MUST be enabled for the doorbell.
- **FR-017**: Event clips MUST be retained for 30 days; continuous footage MUST be retained for 7–14 days, with the exact value tunable per camera and recorded in the NVR config.
- **FR-018**: Event clips MUST be addressable independently of continuous footage so Home Assistant can link to a specific clip.

#### Home Assistant integration

- **FR-019**: A Mosquitto MQTT broker MUST run as a container on HOLYGRAIL inside the Frigate docker-compose stack, reachable by the NVR on the stack's internal network and by Home Assistant over the LAN.
- **FR-020**: The Frigate HA integration MUST be installed via HACS and connected to the MQTT broker.
- **FR-021**: Home Assistant MUST expose per-camera entities for visitor, person, and package detection.
- **FR-022**: An automation MUST fire on doorbell press, delivering a push notification with an inline snapshot image and a clickable link to the live stream/event in the Frigate UI (LAN-only).
- **FR-023**: An automation MUST turn on porch lights when a person is detected at the front door. *(Deferred at deploy 2026-04-18: household has no smart porch light entity in HA yet. Automation stub is committed-but-commented in `contracts/ha-automations.yaml` with a `light.PLACEHOLDER_porch` marker; uncomment + retarget when hardware lands. Tracked in `burn-in-log.md` open follow-ups.)*
- **FR-024**: An automation MUST deliver a push notification with an inline snapshot image and a clickable link to the event clip in the Frigate UI (LAN-only) when a package is detected.
- **FR-024a**: HA notifications in Phase 1 MUST NOT attach full video clips; the clip is reached by following the link on the LAN. This preserves the deferral of remote-access/auth decisions to a later feature.
- **FR-025**: A privacy-mode switch MUST be exposed in HA that, when enabled, pauses recording AND detection on all cameras until toggled off. The restreamer MUST continue to run so that live view remains available to LAN clients (including the native HA Reolink integration) — stopping the restreamer is prohibited because resuming it would re-trigger the Reolink multi-connection firmware bug on simultaneous reconnect.

#### UX

- **FR-026**: The NVR web UI MUST be reachable on the local network via a standard browser (no login gate required within the local network trust boundary of this project).
- **FR-027**: The landing dashboard MUST show a glanceable grid of the most recent event thumbnails across all configured cameras.
- **FR-028**: A vertical timeline view MUST allow browsing past events grouped by day with inline clip playback on thumbnail click.
- **FR-029**: Events MUST be filterable by date range, camera, and object type, with filter state visible in the UI.
- **FR-030**: The UI MUST pass an acceptance test with a non-technical household member reviewing events unassisted (per US-3's Independent Test).

#### Phase 2 readiness

- **FR-031**: Deployment configs MUST contain commented stubs for Phase 2 cameras attached through the Reolink Home Hub, clearly labeled as placeholders.
- **FR-032**: The RTSP/restreamer URL conventions for hub-backed battery/solar cameras MUST be documented (cameras connect through the Hub, not directly).
- **FR-033**: A Phase 2 expansion checklist MUST be committed in `docs/` and MUST be self-service: a future admin should be able to follow it to onboard a new camera without re-reading this spec.

#### Observability & alerting

- **FR-034**: A Camelot Advisor rule MUST monitor free space on the `/mnt/frigate` mount and raise an alert through the existing Advisor → Home Assistant notification-sink path before the volume reaches a configured fill threshold, so the admin is warned before retention caps can be bypassed by overflow.
- **FR-035**: The fill threshold used by FR-034 MUST be recorded in the Advisor threshold table (re-using the Phase 4.5 `alert_thresholds` mechanism), not hard-coded in the rule.
- **FR-036**: A Camelot Advisor rule MUST monitor sustained detection latency on the NVR (signal source: the NVR's own metrics/logs) and raise an alert when P95 latency exceeds a configured threshold for a configured sustained window (default: P95 > 2s for 5 minutes). The detector MUST remain on the GPU — no automatic CPU/Coral failover is performed in Phase 1.
- **FR-037**: The latency threshold and sustained-window parameters used by FR-036 MUST be recorded in the Advisor threshold table (re-using the Phase 4.5 `alert_thresholds` mechanism), not hard-coded in the rule, so they can be tuned without a code change as real-world GPU contention is observed.

### Key Entities

- **NVR Stack**: The set of containerized services providing restreaming, recording, detection, and UI on HOLYGRAIL. Shares the GPU with Ollama. Bound to a config volume and a footage volume.
- **Camera (Phase 1: Reolink Video Doorbell WiFi)**: The single surveillance source in scope. Has a static DHCP reservation, RTSP/ONVIF enabled, and a character-constrained password. Never connected to directly except by the restreamer.
- **Restreamer**: The single upstream connection to each camera. Distributes the stream to the NVR and the native HA Reolink integration. Required to avoid the Reolink multi-connection firmware bug.
- **Detection Event**: An AI-classified motion event (person/car/dog/cat/package) with thumbnail, clip, timestamps, bounding box, and confidence. Surfaced in the web UI and published to MQTT.
- **Continuous Recording**: The rolling 24/7 footage timeline for each camera. Separately retained from event clips.
- **Footage Storage Volume**: The dedicated drive/partition at `/mnt/frigate`. Must enforce retention caps before overflow.
- **MQTT Broker**: The messaging bus bridging the NVR to Home Assistant.
- **Privacy Mode**: A toggled state (via an HA switch) that pauses recording and detection for the whole stack. The restreamer keeps running and live view remains available, so the household can still "see who's at the door" during privacy mode — the switch only controls persistence and AI, not visibility.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Over a 14-day run with the native HA Reolink integration also active, the doorbell experiences zero firmware crashes or multi-connection-bug-induced disconnects, and restreamer health shows no frame drops under normal load.
- **SC-002**: Motion-start to event-visible-in-UI latency is under 1 second at the 95th percentile on the doorbell sub-stream when the GPU is not under simultaneous heavy LLM load.
- **SC-003**: A non-technical household member, given only the NVR URL, completes three event-review tasks (recent activity, a specific day, package filter) unassisted within 3 minutes total on their first use.
- **SC-004**: Doorbell press → phone notification end-to-end latency is under 5 seconds at the 95th percentile during a 50-press test spread over several days.
- **SC-005**: A HOLYGRAIL reboot results in the full NVR stack being available and recording again within 2 minutes of host boot, with no manual intervention.
- **SC-006**: Over a 30-day run, disk usage on `/mnt/frigate` never exceeds 90% because retention caps prune before overflow.
- **SC-007**: Simultaneously serving an Ollama LLM request and running doorbell detection produces no detector crashes and no silent fallback to CPU; logs clearly show detection completed on GPU even if latency degrades.
- **SC-008**: A future admin onboards a hypothetical second camera by following only the Phase 2 expansion checklist, with no need to read the F6.2 source doc or this spec.

## Assumptions

- **MQTT broker placement**: Decided (see Clarifications 2026-04-18) — Mosquitto runs on HOLYGRAIL in the Frigate docker-compose stack.
- **Detection model choice**: Default to the latest stable YOLOv9 variant that is known-good with the chosen NVR's TensorRT pipeline, version pinned in config. Fall back to a YOLOv8 variant only if YOLOv9 is not compatible.
- **Continuous-footage retention default**: 7 days (the floor of the 7–14 day tunable range) to minimize disk pressure; can be tuned up per-camera later based on observed disk usage.
- **Network trust boundary**: The local network (`192.168.10.0/24`) is trusted; the NVR web UI does not need its own authentication gate within Phase 1. Remote access and auth hardening are explicitly deferred to a separate feature.
- **Camera scope**: Phase 1 includes exactly one camera (the Reolink Video Doorbell WiFi). Any second camera — wired or solar — is Phase 2.
- **GPU contention plan**: Detection load on the RTX 2070 Super is light relative to Ollama; no preemption/scheduling layer is added in Phase 1. The FR-036 Advisor latency rule makes the "light load" assumption observable — if it fires repeatedly in production, a detector fallback (CPU or Coral) or an Ollama priority layer is the follow-up.
- **Two-way audio**: Out of scope for Phase 1 (upstream NVR support is still in-progress); the Reolink app covers this case in the interim.
- **Remote access**: Out of scope (will be delivered via a separate Tailscale/reverse-proxy feature).
- **iOS viewer apps** (e.g. Viewu): Out of scope as a product requirement; may be mentioned in the Phase 2 checklist as a nice-to-have.
- **Cloud backup**: Explicitly excluded by design — the system is fully local.
- **Dependency on F6.1**: The Home Assistant integration (F6.1) is already operational; the native Reolink integration inside HA is already consuming the doorbell and will continue to do so through the new restreamer.
- **Dependency on existing infrastructure**: HOLYGRAIL has working Docker, NVIDIA Container Toolkit, and the Ollama stack (Phases 1, 2, 3 of the project plan).
