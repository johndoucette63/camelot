---
description: "Task list for feature 017-frigate-nvr — Frigate NVR + Reolink Doorbell on HOLYGRAIL"
---

# Tasks: Frigate NVR — Local AI Camera Surveillance

**Input**: Design documents in `/Users/jd/Code/camelot/specs/017-frigate-nvr/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included where explicitly required by the plan (pytest for the two new Advisor rules). Per [Constitution IV (Test-After)](../../.specify/memory/constitution.md), tests are written AFTER the implementation task they validate — NOT before. Manual acceptance tests are listed alongside the stories they gate.

**Organization**: Grouped by user story. Each story is independently deployable and independently testable against the story's acceptance criteria in [spec.md](./spec.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable with other [P] tasks in the same phase (different files, no unmet dependencies)
- **[Story]**: US1–US5 maps to the spec user stories
- All paths are absolute from the repo root

## Path Conventions

- **Infrastructure stack**: `infrastructure/holygrail/frigate/` on the Mac (rsync-deployed to `/opt/frigate-stack/` on HOLYGRAIL)
- **Advisor rules**: `advisor/backend/app/services/rules/`
- **Advisor migrations**: `advisor/backend/migrations/versions/`
- **Advisor tests**: `advisor/backend/tests/rules/`
- **Docs**: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the repo directory skeleton for the new stack; prepare secrets and gitignore.

- [X] T001 [P] Create directory `infrastructure/holygrail/frigate/` with subdirectories `config/` and `mosquitto/config/`
- [X] T002 [P] Create placeholder `infrastructure/holygrail/frigate/README.md` summarizing stack purpose and pointing to `specs/017-frigate-nvr/` for the authoritative design
- [X] T003 [P] Create `infrastructure/holygrail/frigate/.env.example` with placeholders: `FRIGATE_DOORBELL_PASSWORD=`, `FRIGATE_MQTT_PASSWORD=`, `HA_MQTT_PASSWORD=`, `FRIGATE_IMAGE_TAG=` (pinned tag chosen at deploy time), `MOSQUITTO_IMAGE_TAG=`
- [X] T004 Add `infrastructure/holygrail/frigate/.env` and `infrastructure/holygrail/frigate/mosquitto/config/passwords` to the repo-root `.gitignore` (two new lines)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Physical, network, and broker foundation that all user stories rely on. No story work should start before this checkpoint.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T005 On HOLYGRAIL: identify the dedicated drive via `lsblk`, format ext4 with label `frigate`, add to `/etc/fstab` with options `defaults,noatime,nofail,x-systemd.device-timeout=10s`, mount at `/mnt/frigate`, `chown 1000:1000 /mnt/frigate` (per research R5 + quickstart Step 3)
- [ ] T006 On the router: add a static DHCP reservation for the Reolink doorbell's MAC. On Pi-hole (`192.168.10.150`): add a local DNS entry `doorbell.lan → <reserved IP>` (per quickstart Step 1)
- [ ] T007 In the Reolink mobile app on the doorbell: enable RTSP and ONVIF (Settings → Network → Advanced); reset the admin password to use ONLY characters from the safe set `a-z A-Z 0-9 @$*~_-+=!?.,:;'()[]`; record the password into `.env` as `FRIGATE_DOORBELL_PASSWORD`. Verify with `ffprobe rtsp://<user>:<pass>@doorbell.lan:554/h264Preview_01_main` from HOLYGRAIL (per quickstart Step 2 + FR-008/FR-009)
- [X] T008 Write `infrastructure/holygrail/frigate/docker-compose.yml` defining two services (`frigate`, `mosquitto`) with pinned image tags from env, `runtime: nvidia` on `frigate`, `restart: unless-stopped` on both, port mappings (Frigate UI 5000, go2rtc 8554 RTSP + 1984 admin, Mosquitto 1884 on LAN), bind mounts to `/opt/frigate-stack/config`, `/opt/frigate-stack/mosquitto/config`, and `/mnt/frigate`. Include Traefik labels routing `frigate.holygrail` to port 5000 (per existing Traefik pattern from Phase 5)
- [X] T009 [P] Write `infrastructure/holygrail/frigate/mosquitto/config/mosquitto.conf` with two listeners — port `1883` bound to the compose internal network only, port `1884` bound to the LAN — plus `password_file /mosquitto/config/passwords` and `acl_file /mosquitto/config/acl` (per research R6)
- [X] T010 [P] Write `infrastructure/holygrail/frigate/mosquitto/config/acl` granting user `frigate` full `frigate/#` read+write and user `homeassistant` read on `frigate/#` + write only on `frigate/+/{detect,recordings,snapshots,motion}/set` (matches `contracts/mqtt-topics.md`)
- [X] T011 [P] Write `infrastructure/holygrail/frigate/mosquitto/config/passwords.example` seed file with commented instructions for regenerating the real `passwords` file via `mosquitto_passwd -c` from the two `.env` variables (`FRIGATE_MQTT_PASSWORD`, `HA_MQTT_PASSWORD`)
- [X] T012 Write `advisor/backend/migrations/versions/009_frigate_thresholds.py` — data-only Alembic migration that inserts two rows into the existing `alert_thresholds` table: (`frigate_storage_high`, `fill_percent`, `>=`, `85`, NULL) and (`frigate_detection_latency`, `p95_ms`, `>=`, `2000`, `300`). Downgrade removes these two rows. No schema changes (per data-model.md)

**Checkpoint**: Foundation ready — `/mnt/frigate` mounted, doorbell reachable via go2rtc-compatible RTSP URL, compose skeleton and Mosquitto config committed, Advisor migration ready to seed thresholds. User story work can now begin.

---

## Phase 3: User Story 1 — Live doorbell view with reliable event recording (Priority: P1) 🎯 MVP

**Goal**: Doorbell streams through go2rtc into Frigate, 24/7 continuous recording lands on `/mnt/frigate`, event clips are retrievable, and the native HA Reolink integration coexists without triggering the multi-connection bug.

**Independent Test**: Ring the doorbell 10× in 10 minutes with the HA Reolink integration active through go2rtc; every press produces a clip; the doorbell never reboots; continuous footage for the full window is on disk (per spec US-1 acceptance scenarios + SC-001).

### Implementation for User Story 1

- [X] T013 [US1] Write `infrastructure/holygrail/frigate/config/config.yml` with the FULL camera pipeline: `mqtt` (pointing to `mosquitto:1883`, user `frigate`, password from `${FRIGATE_MQTT_PASSWORD}`), `detectors.tensorrt` (`type: tensorrt`, `device: 0`), `model` block pointing at `/config/model_cache/yolov9-t-sm75.trt` with `input_tensor: nchw`, `input_pixel_format: rgb`, and `width`/`height` matching the doorbell sub-stream, `go2rtc.streams.doorbell` and `go2rtc.streams.doorbell_sub` pointing at `rtsp://frigate:${FRIGATE_DOORBELL_PASSWORD}@doorbell.lan:554/h264Preview_01_main` and `..._sub`, `cameras.doorbell.ffmpeg.inputs` with record role on main and detect role on sub, `cameras.doorbell.detect.enabled: true`, `cameras.doorbell.objects.track: [person, car, dog, cat, package]`, `cameras.doorbell.record` enabled with `retain.days: 7` and `events.retain.default: 30`, `snapshots.enabled: true` with `retain.default: 30` (per contracts/frigate-config.md + data-model.md + FR-014). Detection is enabled here (not deferred to US2) because Frigate event clips — required by US-1's acceptance test — are a detection feature, not a motion-only feature
- [X] T014 [US1] Generate the YOLOv9-T TensorRT engine for sm_75 BEFORE deploying the stack: on HOLYGRAIL run `docker compose run --rm frigate trt-model-generate` (or the equivalent Frigate helper in the pinned image) against the pinned ONNX source. Confirm `/opt/frigate-stack/config/model_cache/yolov9-t-sm75.trt` appears (~3–5 minutes on RTX 2070 Super). Frigate will refuse to boot in T015 without this file (per research R2)
- [X] T015 [US1] Deploy the stack to HOLYGRAIL: `rsync -av --delete infrastructure/holygrail/frigate/ holygrail:/opt/frigate-stack/`, then on HOLYGRAIL populate `/opt/frigate-stack/.env` from `.env.example`, generate `mosquitto/config/passwords` via `docker run --rm -v ...passwords:/p eclipse-mosquitto mosquitto_passwd -b /p frigate $FRIGATE_MQTT_PASSWORD && ... homeassistant $HA_MQTT_PASSWORD`, then `docker compose pull && docker compose up -d`. Wait for `frigate/available` = `online` in `mosquitto_sub` (per quickstart Step 4)
- [X] T016 [US1] ~~Time-critical~~ **REPLACED by R11**: native HA Reolink integration was REMOVED entirely (see research.md R11 + burn-in-log Deviation 2). go2rtc is now the sole consumer of the doorbell — multi-connection bug class permanently eliminated. No re-point window required.
- [X] T017 [US1] Verify continuous recording by confirming `.mp4` segment files are appearing under `/mnt/frigate/recordings/` and that the Frigate web UI at `http://frigate.holygrail` shows the live stream. Also verify that detection is producing event clips — drop an object in front of the camera and confirm the event appears in the Frigate events feed
- [X] T018 [US1] Implement `advisor/backend/app/services/rules/frigate_storage_high.py` following the pattern of the existing `disk_high.py`. The rule polls HOLYGRAIL's `/mnt/frigate` mount via the existing health-checker infrastructure, reads the threshold row with `rule_name='frigate_storage_high'` from `alert_thresholds`, and fires an alert through the existing Advisor→HA notification-sink path when `fill_percent >= value` (per FR-034/35 + research R7)
- [X] T019 [P] [US1] Write `advisor/backend/tests/rules/test_frigate_storage_high.py` — integration-style pytest that seeds a threshold row, stubs the health-checker's disk reading, and asserts the rule fires exactly when fill crosses the threshold and resolves when it recedes. Create `advisor/backend/tests/rules/` subdirectory if it does not already exist (per Constitution IV test-after + existing rule test pattern)
- [X] T020 [US1] Apply migration 009 on HOLYGRAIL's Advisor: `bash scripts/deploy-advisor.sh && ssh holygrail 'docker exec advisor-backend alembic upgrade head'`; verify the threshold row exists via `psql` (per quickstart Step 8)
- [ ] T021 [US1] Execute the 10-press acceptance test from spec US-1; capture Frigate logs and go2rtc stream health output; confirm zero disconnects, zero firmware reboots, AND at least one event clip per ring in the Frigate event feed. Record results in a new file `specs/017-frigate-nvr/burn-in-log.md` — this file also hosts the 14-day SC-001 observations (started here, continues in the background)

**Checkpoint**: Doorbell is live-streaming through Frigate, 24/7 recording on `/mnt/frigate`, disk-fill alerting wired up. US-1 acceptance scenarios 1–4 pass. MVP is viewable — the household can open `http://frigate.holygrail` and see the doorbell.

---

## Phase 4: User Story 2 — GPU-accelerated AI detection (Priority: P1)

**Goal**: YOLOv9-T TensorRT detection on the RTX 2070 Super against the doorbell sub-stream, tracking exactly `person`, `car`, `dog`, `cat`, `package`. Sub-second P95 latency under non-contention; no silent CPU fallback.

**Independent Test**: Walk into frame, place a package, let a car pass, walk a dog past — each labeled correctly in the event feed within seconds. `nvidia-smi` shows Frigate on the GPU (per spec US-2 + SC-002/SC-007).

### Implementation for User Story 2

- [X] T022 [US2] ~~Verify GPU usage~~ **DEVIATION 1 — CPU detector instead of GPU**. Frigate 0.16+ removed the standalone TensorRT detector; pivoting to ONNX+CUDA hit super-gradients/numpy/onnxruntime kernel walls. Shipped with bundled `cpu_model.tflite` at 9.72 ms inference (well under 1000 ms SLO). FR-011 deferred to follow-up; SC-002 still passes. See burn-in-log Deviation 1.
- [ ] T023 [US2] Capture a P95 detection-latency sample to explicitly close SC-002: with Ollama idle, pull `/api/stats` every 5 seconds for 15 minutes while varying motion in front of the doorbell (idle stretches + 5 walk-throughs). Compute P95 of the `inference_speed` series. Record P95 value, sample count, and start/end timestamps in `specs/017-frigate-nvr/burn-in-log.md` under a new `SC-002` section. Pass criterion: P95 < 1000 ms. If the test fails, raise an issue; do NOT proceed to T024 until root-caused or the FR-015/SC-002 target is renegotiated in the spec (per SC-002)
- [ ] T024 [US2] Walkthrough acceptance test: walk into frame (expect `person`), place a cardboard package (expect `package`), drive a car past (expect `car`), then move an untracked object (e.g., shopping cart) through frame and confirm NO event is generated (per FR-014 + US-2 scenarios 1 and 3)
- [ ] T025 [US2] Contention test: start a sustained Ollama chat completion (`ollama run llama3.1 "write a 2000 word essay"` or similar), then trigger detection; confirm detection still completes, logs show GPU (not CPU) inference, no detector crash (per US-2 scenario 2 + SC-007)
- [X] T026 [US2] Implement `advisor/backend/app/services/rules/frigate_detection_latency.py` — poll Frigate `/api/stats` on the health-checker cadence, extract per-camera `inference_speed`, maintain a rolling window per-camera, compute P95 over `window_seconds` from the threshold row, and fire an alert when P95 ≥ threshold sustained over the window. Reuses the Advisor → HA notification-sink path. Threshold row is already seeded by migration 009 from T012 (per FR-036/37 + research R7)
- [X] T027 [P] [US2] Write `advisor/backend/tests/rules/test_frigate_detection_latency.py` — integration pytest that feeds synthetic P95 sequences (staying below / crossing / recovering) into the rule's buffer and asserts fire/resolve transitions. Create `advisor/backend/tests/rules/` subdirectory if it does not already exist (per Constitution IV test-after)

**Checkpoint**: Detection on GPU working, correct object classes tracked, latency rule armed. US-2 acceptance scenarios 1–3 pass.

---

## Phase 5: User Story 3 — Wife-friendly event review UX (Priority: P1) — RELEASE GATE

**Goal**: A non-technical household member can open `http://frigate.holygrail`, see recent activity, scrub through a vertical timeline, and filter by date/camera/object — all without guidance.

**Independent Test**: The 3-task scripted acceptance test from spec US-3 (recent activity / specific day / package filter) — household member completes all three unassisted within 3 minutes (per SC-003).

### Implementation for User Story 3

- [X] T028 [US3] Verify Traefik routing works end-to-end: `http://frigate.holygrail` on a LAN device (phone, laptop) resolves and loads the Frigate UI. Traefik labels were added in T008 (this task is verification, not reconfiguration)
- [ ] T029 [US3] Sanity-check the UX surface on a mobile browser (iOS Safari + an Android Chrome if available) — confirm the landing dashboard renders, timeline scrolls, filters are reachable (per FR-026 through FR-029)
- [ ] T030 [US3] Wait for at least 48 hours of events to accumulate so the timeline/filters have content to browse (per US-3 acceptance scenario 1 precondition)
- [ ] T031 [US3] **Release-gate acceptance test**: Give the NVR URL to a non-technical household member who has never seen the system. Without coaching, ask them the three questions from spec US-3 Independent Test (recent 24h; yesterday afternoon; package this week). Observe, time, and record friction points in `specs/017-frigate-nvr/wife-test-log.md`. All three must complete unassisted within 3 minutes total (per SC-003)

**Checkpoint**: US-3 passes or fails. This is the feature's release gate — if it fails, do NOT proceed to US4 until the UX friction is understood and (if fixable in config) addressed.

---

## Phase 6: User Story 4 — Home Assistant integration with rich notifications (Priority: P2)

**Goal**: Detections flow into HA via MQTT, privacy switch works, three automations deliver the notifications and porch-light behaviors required by spec.

**Independent Test**: Press doorbell → phone notification with snapshot + link within 5s. Walk up → porch lights on within 3s. Drop a package → clip-link notification. Toggle privacy → subsequent motion produces no events until toggled off (per spec US-4 acceptance scenarios 1–4 + SC-004).

### Implementation for User Story 4

- [X] T032 [US4] On the HA host: install the HACS Frigate integration. Pivoted to **Mosquitto bridge architecture (R12)** instead of HA pointing at HOLYGRAIL Mosquitto directly — HA's MQTT integration is `single_instance_allowed` and serving WeeWX. Bridge config in `/opt/frigate-stack/mosquitto/config/conf.d/bridge.conf` forwards `frigate/#` topics to HA's local broker; HACS Frigate integration consumes from there. Frigate API URL: `http://192.168.10.129:5000` (direct, not via Traefik — HA host doesn't use Pi-hole DNS). See burn-in-log Deviation 3.
- [X] T033 [US4] Copy the `input_boolean.frigate_privacy_mode` block from `specs/017-frigate-nvr/contracts/ha-automations.yaml` into the HA config's `input_boolean:` section; reload
- [X] T034 [US4] Copy automations from `specs/017-frigate-nvr/contracts/ha-automations.yaml` into HA's `automations.yaml`. Final shape after R11 architecture pivot: privacy ON, privacy OFF, person-at-door notify (replaces button-press notify), package notify, **plus** `notify.household` group fanning out to all four paired iOS devices. Porch-lights automation is committed-but-commented (no smart porch light entity yet, see FR-023 deferral note). Reload via Developer Tools → YAML → Reload Automations
- [X] T035 [US4] Privacy-mode round-trip test: PASS. HA toggle ON → Frigate `detect.enabled` and `record.enabled` both flipped True→False; toggle OFF → restored True/True. detection_fps fell 5.2 → 1.6 in privacy mode (motion-only, no AI). Restreamer (go2rtc) never paused (per Clarification Q3). Verified end-to-end via `/api/stats` diff; results in `burn-in-log.md`.
- [X] T036 [US4] End-to-end notification tests: walk-in-front-of-doorbell triggered the person event (ID `1776550155.809935`); notification arrived on all 4 paired iOS devices (`notify.household`) with inline snapshot image and tap-target opening Frigate UI at `http://192.168.10.129:5000`. Note: original "doorbell button press" trigger was replaced with "person detected" per R11; doorbell button press still rings the chime (hardware-paired via Reolink app, independent of HA). Package and porch-light tests deferred (no test package + no smart porch light yet).
- [X] T037 [US4] ~~Regression sanity check~~ **OBSOLETED by R11**: native HA Reolink integration was removed during deploy. go2rtc is now sole consumer of the doorbell. Single producer per camera verified in `/api/streams`.

**Checkpoint**: HA integration fully functional. US-4 passes.

---

## Phase 7: User Story 5 — Phase 2 expansion readiness (Priority: P3)

**Goal**: A future admin can onboard a Reolink Home Hub plus solar cameras through a config-only change, following a self-service checklist.

**Independent Test**: A reader of `docs/frigate-phase2-expansion.md` alone can onboard a hypothetical second camera without referring to `spec.md` or `F6.2-frigate-nvr.md` (per SC-008).

### Implementation for User Story 5

- [X] T038 [US5] Add commented Phase 2 camera stubs to `infrastructure/holygrail/frigate/config/config.yml` per `contracts/frigate-config.md`: `go2rtc.streams` entries for `solar_cam_front{,_sub}` and `solar_cam_side{,_sub}` pointing at `hub.lan:554/h264Preview_0{1,2}_{main,sub}`, plus matching commented `cameras.solar_cam_front` and `cameras.solar_cam_side` blocks. All stubs MUST be valid YAML when uncommented (per FR-031, FR-032)
- [X] T039 [US5] Add a `FRIGATE_HUB_PASSWORD=` placeholder line to `infrastructure/holygrail/frigate/.env.example` (commented, labeled `# PHASE 2`) so the Phase 2 password is anticipated in the secrets contract
- [X] T040 [US5] Write `docs/frigate-phase2-expansion.md` — a self-contained checklist covering: (a) Home Hub DHCP reservation + `hub.lan` Pi-hole entry; (b) Hub password set to Reolink-safe character set; (c) Enable RTSP/ONVIF on the hub; (d) Uncomment the Phase 2 stubs in `config.yml`; (e) Assign the next `h264Preview_<channel>_*` number per camera; (f) `docker compose restart frigate`; (g) HA picks up new camera entities automatically; (h) Update the Advisor storage-fill threshold if the drive is now undersized (per FR-033)
- [ ] T041 [US5] Checklist self-test: read `docs/frigate-phase2-expansion.md` end-to-end WITHOUT referring to spec.md, F6.2, or this plan. If any step is unclear, update the checklist. This is a subjective-but-enforced gate (per SC-008)

**Checkpoint**: Phase 2 expansion is a documented, low-risk future config change. US-5 passes.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T042 [P] Update `docs/INFRASTRUCTURE.md`: add Frigate, go2rtc, and Mosquitto rows to the HOLYGRAIL "Deployed Services" table; add Traefik hostname entry `frigate.holygrail` to the "Service Hostnames" table
- [X] T043 [P] Update `docs/PROJECT-PLAN.md`: mark F6.2 as complete and cross-reference this spec directory
- [ ] T044 [P] Add a minimal Grafana dashboard panel (or InfluxDB write point in the existing monitoring stack) for `frigate_detection_fps` and `/mnt/frigate` fill percent. Best-effort per Constitution V ("new services SHOULD ship with a basic Grafana dashboard"); not gated on
- [ ] T045 Run the full [quickstart.md](./quickstart.md) end-to-end as a final validation pass (per `feedback_quickstart_after_implement.md` memory)
- [ ] T046 Update `MEMORY.md` (via a new `project_` memory file) ONLY if the burn-in produced surprising findings — e.g., a detection-model variant that failed, a Reolink password character that slipped through, or recurring GPU contention. If nothing surprising, leave memory untouched
- [ ] T047 Git commit the feature changes and merge `017-frigate-nvr` → `master` per the project's single-developer workflow

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. BLOCKS all user stories.
- **Phase 3 (US1)**: Depends on Phase 2. Now owns the complete `config.yml` including the detector, so subsequent phases can verify rather than edit it.
- **Phase 4 (US2)**: Depends on Phase 3 having a running detector. No `config.yml` edits in this phase — US2 is verification + tuning + the latency rule.
- **Phase 5 (US3)**: Depends on Phase 4 because the non-technical UX test is most meaningful once detections are producing real events.
- **Phase 6 (US4)**: Depends on Phase 4 (needs MQTT events flowing). Can run in parallel with Phase 5's UX test.
- **Phase 7 (US5)**: Depends on Phase 4 (so the Phase 2 stubs follow the same `config.yml` shape that's now proven). Can run in parallel with Phase 6.
- **Phase 8 (Polish)**: Depends on all desired user stories completing.

### User Story Dependencies

- **US1 (P1)**: No upstream story dependencies beyond Foundational.
- **US2 (P1)**: Verifies and tunes US1's detector configuration. Does not edit `config.yml`. Sequential only because it needs the detector actually running.
- **US3 (P1)**: Functionally independent of US1/US2 (UI is built-in), but the acceptance test needs real events, which means US1+US2 must be live.
- **US4 (P2)**: Depends on US1 (MQTT bus) + US2 (detection events). Does not modify `config.yml`.
- **US5 (P3)**: Extends `config.yml` with COMMENTED stubs — parallel-safe with US4 as long as edits don't happen in the same git operation.

### Within Each User Story

- Config edits before deploy
- Deploy before verification
- Implementation before pytest (Test-After, per Constitution IV)
- Each story ends with a manual acceptance test that gates the next phase

### Parallel Opportunities

- All `[P]` tasks in Phase 1 (T001, T002, T003) touch different files and can run together.
- In Phase 2: T009, T010, T011 all touch different files in `mosquitto/config/` and are `[P]`.
- In Phase 3: T019 (test file) is `[P]` with the other Phase 3 tasks once T018 (the rule code) is done.
- In Phase 4: T027 (test file) is `[P]` with the other Phase 4 tasks once T026 (the rule code) is done.
- Phase 5 (UX test) and Phase 6 (HA wiring) and Phase 7 (Phase 2 docs) can run on different days by the same developer — they do not share files.
- In Phase 8: T042, T043, T044 are all `[P]` (different files).

---

## Parallel Example: Phase 2 (Foundational)

```bash
# After T005–T008 complete (drive, DHCP, doorbell, compose.yml), these three
# can be authored concurrently since they each touch their own file:
Task: "Write mosquitto.conf with two-listener + ACL setup"            # T009
Task: "Write mosquitto ACL file with frigate + homeassistant users"   # T010
Task: "Write mosquitto passwords.example with regeneration recipe"    # T011
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Complete Phase 1 (Setup) — 4 tasks, mostly file scaffolding.
2. Complete Phase 2 (Foundational) — 8 tasks, including the irreversible hardware/router/doorbell steps.
3. Complete Phase 3 (US1) — 9 tasks through the 10-press burn-in.
4. **STOP and VALIDATE**: MVP is live. Doorbell streams, records, and survives coexistence with the native HA integration.
5. Start the background 14-day SC-001 burn-in while moving to US2.

### Incremental Delivery

- After Phase 3: doorbell is live + recorded (MVP).
- After Phase 4: detections are intelligent — the NVR is a smart NVR, not a dumb recorder.
- After Phase 5: the household can actually use the thing (release gate).
- After Phase 6: phones buzz and porch lights flick on.
- After Phase 7: future you thanks present you for the Phase 2 stubs.
- After Phase 8: docs updated, monitoring dashboard landed, feature merged to master.

### Single-Developer Strategy

Matches the project's reality: one developer, no parallelism across humans. Parallel opportunities inside a single phase are useful because they mean "any of these can be next — pick whichever file you feel like touching" rather than "start three PRs simultaneously".

---

## Notes

- Tests come AFTER implementation per Constitution IV (Test-After). Tasks T019 and T027 are written after the rule code they validate, not before.
- Secrets (`.env`, mosquitto `passwords`) are never committed; they are generated on HOLYGRAIL from the `.env.example` template.
- The 14-day SC-001 burn-in runs in the background — don't block story completion on it, but log results in `burn-in-log.md` and revisit if any Reolink-bug signal appears.
- UI and doorbell tests are manual. That is expected for an infrastructure feature and does not violate Constitution IV — automated tests exist where automation adds real value (the two Advisor rules).
- Per the memory [`reference_advisor_deploy.md`](../../../.claude/projects/-Users-jd-Code-camelot/memory/reference_advisor_deploy.md): deploy Advisor via `bash scripts/deploy-advisor.sh` — never `git pull` on HOLYGRAIL.
- Per memory [`feedback_quickstart_after_implement.md`](../../../.claude/projects/-Users-jd-Code-camelot/memory/feedback_quickstart_after_implement.md): T045 (run quickstart end-to-end) is the final gate.
