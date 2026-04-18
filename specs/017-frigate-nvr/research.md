# Phase 0 Research: Frigate NVR

**Feature**: 017-frigate-nvr
**Date**: 2026-04-18

This document resolves the open technical questions needed before design (Phase 1) can proceed. Each section ends with a **Decision** that the rest of the plan treats as locked in.

---

## R1. Frigate image + TensorRT variant

**Question**: Which Frigate image variant and tag should be pinned?

**Decision**: `ghcr.io/blakeblackshear/frigate:stable-tensorrt` pinned to a specific semver tag captured at deploy time and recorded in `infrastructure/holygrail/frigate/docker-compose.yml`. The `-tensorrt` variant is required because Phase 1 mandates the NVIDIA TensorRT detector (FR-011/FR-012).

**Rationale**:
- The `-tensorrt` image ships the TensorRT runtime and model-generation tooling; the plain `stable` image does not.
- Pinning to a specific tag (not `:stable` floating) is required by FR-001 (image tags pinned) and protects against silent detector-API changes during routine `docker compose pull`.
- The tag value itself is captured at the moment the feature is actually deployed (a planning artifact, not a spec-kit decision), so this document records the **policy**, not the literal string.

**Alternatives considered**:
- Plain `stable` + manual CUDA/TRT install — rejected; duplicates upstream work and violates Constitution III (containerized everything).
- Nightly/beta tags — rejected; the project values stability (Constitution II) and the bleeding-edge detector work on YOLOv9 is now in the `stable-tensorrt` line.

---

## R2. Detection model (YOLOv8 vs YOLOv9) — superseded during deploy, see also burn-in-log

**Original decision (2026-04-18 planning phase)**: YOLOv9-T (tiny) generated at first container boot via Frigate's `trt-model-generate` helper for `sm_75` (RTX 2070 Super's compute capability), with the generated `.trt` engine committed to `/opt/frigate/config/model_cache/` and the model name + generation parameters recorded in `config.yml`.

**Deploy reality (2026-04-18 deploy session)**: superseded. Frigate 0.16+ removed the standalone TensorRT detector — the `stable-tensorrt` image no longer ships the `tensorrt` Python package; `TRT_SUPPORT = False` evaluates inside the detector plugin. GPU detection now goes through the **`onnx` detector** with `onnxruntime`'s TensorrtExecutionProvider/CUDAExecutionProvider, which expects an ONNX file (with NMS baked in for `yolonas`/`yologeneric`) rather than a pre-built TensorRT engine.

**Phase 1 deploy choice**: ship with Frigate's bundled **`cpu` detector** (SSD MobileNet on COCO-90, `cpu_model.tflite`) — measured at 9.72 ms inference latency on the Ryzen 7800X3D for a single 320×320 sub-stream, well under the 1000 ms SC-002 SLO. This satisfies SC-002 but technically violates FR-011's "GPU detection". Documented as **Deviation 1** in `burn-in-log.md`. GPU detection upgrade tracked as a focused follow-up.

**Why we didn't ship GPU detection on Day 1**:
- `super-gradients==3.7.1` (the standard YOLO-NAS-S export tool) pins `numpy<=1.23`, conflicting with `onnxruntime>=1.15`'s `numpy>=1.24.2` requirement.
- Older `onnxruntime` (1.15.0) shared object fails on the modern HOLYGRAIL kernel: `cannot enable executable stack as shared object requires`.
- Sourcing a pre-exported YOLO-NAS-S/YOLOv9-T ONNX from public mirrors hit 404s.
- Time-boxed call: get the rest of the stack validated end-to-end with CPU; tackle GPU as its own focused work.

**Follow-up GPU path**: target the `onnx` detector with YOLO-NAS-S (Frigate's first-class GPU model, `model_type: yolonas`, Apache-2.0 licensed, better Ryzen+RTX accuracy than YOLOv9-T at comparable latency). Generate ONNX in a clean Docker container with a working super-gradients/torch/onnxruntime triple, drop into `/opt/frigate-stack/config/model_cache/`, swap detector type in `config.yml`, restart Frigate.

**Alternatives considered (still applicable to follow-up)**:
- **YOLOv9-T ONNX with `model_type: yologeneric`** — works in current Frigate but less first-class than yolonas. AGPL-3.0 license. Fallback if YOLO-NAS-S has accuracy issues for the package class.
- **Coral TPU** — rejected; no Coral hardware in the project, GPU is working.

---

## R3. go2rtc: standalone vs Frigate-bundled

**Question**: Should go2rtc be a separate container sidecar or the one bundled inside Frigate?

**Decision**: Use Frigate's bundled go2rtc (Frigate 0.13+ ships it) and configure it through Frigate's `go2rtc:` block in `config.yml`. Expose go2rtc's admin UI on port 1984 via Traefik hostname `go2rtc.holygrail` (following the existing Traefik pattern from Phase 5).

**Rationale**:
- One fewer container to maintain (Constitution II).
- Frigate and go2rtc share config lifecycle and restart together, eliminating a class of "one is up, the other is not" incidents.
- Bundled go2rtc still exposes its UI and API, so health verification and debugging (US-2 acceptance) are unaffected.
- HA's native Reolink integration reads from `rtsp://holygrail:8554/doorbell` (go2rtc's stream path) — it doesn't care whether go2rtc is in its own container or bundled.

**Alternatives considered**:
- Sidecar go2rtc — rejected; adds orchestration surface for no functional gain at Phase 1 scale.

---

## R4. Doorbell RTSP URL structure + Phase 2 hub-backed pattern

**Question**: What is the exact RTSP URL pattern for the Reolink Video Doorbell WiFi, and what does the Phase 2 Home-Hub pattern look like?

**Decision**:
- **Doorbell (Phase 1, direct Wi-Fi)**: Main stream `rtsp://<user>:<pass>@<doorbell-ip>:554/h264Preview_01_main`, sub-stream `rtsp://<user>:<pass>@<doorbell-ip>:554/h264Preview_01_sub`. `<doorbell-ip>` resolves to the router's DHCP reservation hostname, not a literal IP, so a subnet re-ip does not break config.
- **Phase 2 (hub-backed cameras behind a Reolink Home Hub)**: `rtsp://<user>:<pass>@<hub-ip>:554/h264Preview_<channel>_<main|sub>` where `<channel>` increments per camera (`01`, `02`, …). All hub-backed cameras share the hub's IP and differ only by channel number.

**Rationale**:
- The doorbell uses Reolink's standard `h264Preview_01_{main,sub}` path. Confirmed by the native HA Reolink integration's existing URL pattern (which already works against the doorbell today).
- Hub-backed cameras multiplex their streams through the hub's RTSP server with per-channel paths — this is the documented Reolink convention that motivated the "commented stubs for Phase 2" requirement (FR-031).
- Recording this up front prevents a Phase 2 rewrite when solar cameras arrive (risk explicitly called out in the source feature doc).

**Alternatives considered**:
- ONVIF profile URLs — rejected for the primary path; RTSP URLs are simpler and go2rtc consumes them directly. ONVIF stays enabled on the doorbell (FR-008) for future features (motion-sensor passthrough, PTZ control on solar cameras) but isn't used as the stream source.

---

## R5. `/mnt/frigate` drive selection and filesystem

**Question**: What drive backs `/mnt/frigate`, and what filesystem should it be?

**Decision**: Dedicate a separate SATA SSD or large-capacity HDD (≥2 TB recommended) already installed in HOLYGRAIL, formatted as **ext4** with `noatime`, mounted at `/mnt/frigate` via `/etc/fstab` with `nofail,x-systemd.device-timeout=10s` so a disk fault does not block boot. Ownership set to `uid=1000,gid=1000` to match the container user (avoids `:z` SELinux labeling on Ubuntu, irrelevant on this host anyway).

**Rationale**:
- ext4 is the project's default (matches existing HOLYGRAIL disks, INFRASTRUCTURE.md).
- `noatime` reduces metadata writes for a write-heavy workload (continuous recording).
- `nofail,x-systemd.device-timeout=10s` means a disk removal or fault surfaces as degraded operation (Frigate will log and eventually alert via FR-034) instead of a failed boot that blocks Ollama, Plex, and everything else.
- The actual physical drive choice is a hardware task recorded in `quickstart.md` — the plan locks in the mount point + filesystem + fstab options, not the drive serial number.

**Alternatives considered**:
- ZFS or btrfs — rejected (Constitution II Simplicity; ext4 is sufficient and the project has no other ZFS/btrfs users to share admin burden with).
- Storing on the OS NVMe — rejected; 98 GB LVM is far too small for 24/7 recording (SC-006 disk headroom would be impossible).
- Storing on the NAS over SMB — rejected; random-write latency is too high for continuous recording and cifs is known to corrupt sqlite journals Frigate uses internally.

---

## R6. Mosquitto configuration and credentials

**Question**: How is Mosquitto configured, who authenticates, and what do the listeners look like?

**Decision**: Mosquitto 2.x with two listeners:
- `1883` on the docker-compose internal network only (Frigate↔Mosquitto) — no LAN exposure beyond Docker.
- `1884` on the LAN — reachable by Home Assistant. ACL restricts the `homeassistant` user to read-only on `frigate/#` topics + write on `frigate/+/{set,snapshot_set}`.

Auth: two users (`frigate`, `homeassistant`) in a `passwords` file, both seeded from env vars at first-boot (entrypoint script). The passwords file is bind-mounted and gitignored.

**Rationale**:
- Two listeners cleanly separate "trusted internal" traffic from "LAN clients" without needing TLS for the internal hop.
- Per-user ACLs are cheap to add at setup time and prevent accidental cross-writes if a future integration is added.
- Seed-from-env at first boot means no plaintext credential ever lands in the repo (Constitution III).

**Alternatives considered**:
- Anonymous Mosquitto on a single listener — rejected; violates Constitution V (observability) where auth failures are a meaningful signal, and leaves the broker vulnerable if the LAN boundary is ever loosened.
- TLS between Mosquitto and HA — deferred; LAN trust boundary (Assumptions in spec) makes this overkill for Phase 1.

---

## R7. Detection-latency metrics source

**Question**: Where does the Advisor's FR-036 latency rule get its P95 data from?

**Decision**: Frigate's `/api/stats` HTTP endpoint, polled by the Advisor health-checker on the existing poll cadence (already polls `ollama`, `service_down`, etc.). `/api/stats` exposes per-camera `detection_fps` and `inference_speed` plus a rolling latency distribution that the rule post-processes into a P95 over a sliding window. The window size + threshold are the two `alert_thresholds` rows seeded by migration 009.

**Rationale**:
- Frigate already exposes these metrics natively on its API; no need to add Prometheus or a metrics sidecar (Constitution II).
- Using HTTP (not MQTT) means the rule works even if Mosquitto is unreachable — detection can be degrading for reasons unrelated to the MQTT bus, and the rule should fire regardless.
- Fits the existing Advisor rule pattern (HTTP poll → threshold compare → alert) — `ollama_unavailable.py` and `service_down.py` already follow this shape.

**Alternatives considered**:
- Subscribing to the MQTT `frigate/stats` topic — rejected; couples the Advisor rule's liveness to the MQTT bus and creates a dead-man if Mosquitto dies.
- Scraping Frigate logs for latency — rejected; fragile against log-format changes upstream.
- Adding Prometheus + node_exporter + a scraper — rejected; big new surface for one rule.

---

## R8. GPU sharing with Ollama

**Question**: Can Frigate and Ollama share the RTX 2070 Super safely, and do we need any scheduler?

**Decision**: Both containers request the GPU via `runtime: nvidia` (NVIDIA Container Toolkit default) with **no** MIG, no MPS, no manual VRAM caps. Detection uses ~1 GB VRAM for YOLOv9-T; Llama 3.1 8B uses ~5–6 GB; the RTX 2070 Super has 8 GB total, leaving small but workable headroom.

The observability rule FR-036 exists precisely to falsify this assumption if it turns out wrong in practice — if P95 latency breaches fire repeatedly under real load, a follow-up feature will add either a priority scheduler or offload Ollama to a second GPU.

**Rationale**:
- MIG is not supported on consumer GeForce cards (Ampere data-center only).
- MPS helps with concurrent CUDA kernels but adds operational complexity (an MPS control daemon) that Constitution II discourages for a hypothesized problem.
- The latency rule (FR-036) makes the "it's fine" assumption measurable, which is the Constitution V-aligned answer: observe first, scheduler later if needed.

**Alternatives considered**:
- MPS daemon — rejected (complexity without proven need).
- Nvidia Toolkit `--gpus '"device=0"'` capacity fractions — not supported for consumer cards.
- CPU fallback detector configured as secondary — rejected per Clarification Q5 (spec explicitly chose observability-only, no automatic failover).

---

## R9. Native HA Reolink integration re-point

**Question**: How does the existing HA Reolink integration get moved off the doorbell and onto go2rtc without causing downtime or re-triggering the multi-connection bug?

**Decision**: Sequencing, executed during the deploy window documented in `quickstart.md`:

1. Deploy Frigate stack; verify go2rtc has a stable connection to the doorbell with the native HA Reolink integration still pointing at the camera directly (two upstream connections temporarily — the known-bad state the deploy is *escaping*; tolerate it for the next 30 seconds).
2. In Home Assistant, immediately switch the Reolink integration's camera URL to `rtsp://holygrail:8554/doorbell` (go2rtc) and restart HA.
3. Verify via `docker exec frigate go2rtc` that exactly one upstream connection is present.
4. Verify the doorbell has not rebooted (watch logs or the Reolink app's "last seen" timestamp).

The tolerated ~30 seconds of dual connection is lower risk than the alternatives because the Reolink bug triggers on sustained dual access, not on a brief overlap.

**Rationale**:
- The existing HA integration consumes the doorbell today; this feature must not break that integration mid-deploy.
- Any sequencing that stops the HA integration first would leave the household without the doorbell press notification during the deploy — explicitly worse than 30 seconds of dual access.

**Alternatives considered**:
- Disable the HA Reolink integration entirely, deploy Frigate, then re-enable pointed at go2rtc — rejected; Reolink-integration-offline means the doorbell button press produces no HA event during the deploy window (user-visible outage).
- Deploy Frigate pointed at a placeholder stream, then swap — rejected; unnecessary complexity.

---

## R10. Privacy-mode implementation (per Clarification Q3)

**Question**: Given privacy mode pauses recording + detection only (not the restreamer), what mechanism in Frigate's config realizes that?

**Decision**: Privacy mode is implemented as an MQTT switch exposed by Frigate itself — `frigate/<camera>/recordings/set` and `frigate/<camera>/detect/set` (Frigate's native `set` topics). The HA switch entity fires both sets to `OFF` when privacy is on, `ON` when off. The go2rtc stream is never touched.

**Rationale**:
- Frigate's native `set` topics are the supported mechanism for this exact use case; no custom scripting required.
- Matches the spec's FR-025 requirement that the restreamer must continue running.
- HA switch → MQTT → Frigate reaction is sub-second in practice.

**Alternatives considered**:
- Frigate's global `frigate/<camera>/privacy/set` (single topic) — not implemented upstream on all Frigate versions; rejected for portability.
- Stopping and starting the Frigate container on privacy toggle — rejected; slow, would interrupt go2rtc.

---

## R11. HA architecture pivot — remove native Reolink integration entirely (supersedes R9)

**Question** (raised mid-deploy): does it make more sense to re-point HA's existing native Reolink integration onto go2rtc (R9 plan), or just remove the Reolink integration and let Frigate be the single source of camera-related signals in HA?

**Decision**: remove the native HA Reolink integration. Frigate (via the HACS Frigate integration) becomes the single source of all camera-related signals in HA — events, snapshots, recordings, sensors, switches.

**Rationale**:
- One source of truth — eliminates the "weird parallel path" of two integrations talking about the same physical device.
- Permanently kills the Reolink multi-connection firmware bug class — only go2rtc ever connects to the doorbell.
- The audible chime is hardware-paired with the doorbell via the Reolink mobile app, so the household-critical "ding" path is unaffected by HA changes.
- The discrete "doorbell button was pressed" event is replaced by Frigate's "person detected at the doorbell" trigger — arguably better UX (catches drop-off delivery drivers who don't ring).

**Cost paid**:
- Lost the discrete doorbell-press event in HA. If ever specifically wanted, recoverable later via go2rtc ONVIF event proxy or a small ONVIF→MQTT shim.
- Lost Reolink-specific entities (battery state, Wi-Fi signal). Cosmetic for a wired doorbell.

**Spec impact**: FR-022 trigger semantic revised in `contracts/ha-automations.yaml` (now `frigate/events` filtered to `camera=doorbell, label=person, type=new`).

**Alternatives considered**:
- R9's "re-point HA Reolink integration's stream URL to go2rtc within a 30-s window" — viable, but still leaves two integrations talking to the same camera, and the re-point itself is fragile across Reolink integration UI changes. Rejected.
- "Disable the camera entity in the Reolink integration but keep the events" — uncertain whether HA's Reolink integration honors that without still pulling RTSP. Rejected (untested).

---

## R12. MQTT broker topology — bridge HOLYGRAIL Mosquitto to HA's existing add-on (supersedes R6's "HA points at our broker" assumption)

**Question** (raised mid-deploy): how does HA's MQTT integration consume Frigate topics when HA's MQTT integration is `single_instance_allowed` and is already configured against the HA-OS Mosquitto add-on (serving WeeWX)?

**Decision**: configure a Mosquitto **bridge** from HOLYGRAIL Mosquitto → HA's local Mosquitto add-on. Frigate publishes to HOLYGRAIL Mosquitto (close, low-latency, in-stack); the bridge forwards `frigate/#` topics OUT to HA's broker; HA's existing MQTT integration sees them as native. The bridge also forwards `frigate/+/{detect,recordings,snapshots,motion}/set` IN so HA-driven privacy-mode toggles reach Frigate.

**Rationale**:
- HA's MQTT integration is `single_instance_allowed` (verified during deploy via the Add Integration dialog). Cannot have two separate MQTT integrations for two brokers.
- Existing HA broker has 14 entities (WeeWX) actively in use — re-pointing the existing MQTT integration to HOLYGRAIL would orphan them.
- Bridging is the standard Mosquitto pattern for this exact scenario; both brokers run independently, each remains the source of truth for its locally-published topics, and the bridge moves whatever subset of topics is needed.

**Implementation**:
- Bridge user `holygrail_bridge` created in HA's Mosquitto add-on Logins config.
- Bridge config at `/opt/frigate-stack/mosquitto/config/conf.d/bridge.conf` (gitignored — contains the bridge credentials).
- HOLYGRAIL Mosquitto's `mosquitto.conf` (in repo) has `include_dir /mosquitto/config/conf.d` so any local override file is loaded.
- Topics: `frigate/# out 0` + `frigate/+/{detect,recordings,snapshots,motion}/set in 0`. Surgical subscriptions both ways prevent bridge loops.

**Alternatives considered**:
- Re-point HA's MQTT integration to HOLYGRAIL and migrate WeeWX → HOLYGRAIL too — viable long-term consolidation but requires reconfiguring the WeeWX publisher (out of scope for 017). Rejected for Phase 1.
- Run only one Mosquitto (HA's local) and have Frigate publish there directly — would require Frigate to reach across the LAN to HA's broker on every publish, adding latency and a fragile dependency. Rejected.

---

## Open items intentionally left for later

- **Exact Frigate image tag string** (R1): captured at deploy time in `docker-compose.yml`, not in this research.
- **Exact physical drive choice for `/mnt/frigate`** (R5): recorded in the deployed `quickstart.md` after inspecting HOLYGRAIL's current disk inventory.
- **Retention tuning per camera** (spec default: 7 days continuous, 30 days events): values live in `config.yml` and can be tuned against observed disk usage without re-running `/speckit.plan`.

All spec `NEEDS CLARIFICATION` markers resolved (none were raised in the spec; all assumptions are locked in here).
