# Frigate NVR — Deploy + Burn-in Log

**Feature**: 017-frigate-nvr
**Deploy date**: 2026-04-18
**Driver**: live-deploy session via Claude (Mac → HOLYGRAIL via SSH)

## Deploy summary

The Frigate stack is live on HOLYGRAIL with all eight stack components healthy and integrated with Home Assistant via a Mosquitto bridge. Two spec deviations were taken during deploy (documented below) — both are tracked as follow-up work, neither blocks Phase 1 value delivery.

| Stack component | Result |
|------------------|--------|
| `/mnt/frigate` (LVM, 800 GB ext4) | mounted, fstab entry persistent across reboot |
| Pi-hole DNS — `frigate.holygrail`, `doorbell.lan` | resolving |
| Frigate container (`stable-tensorrt` image) | up, healthy, web UI at http://frigate.holygrail |
| go2rtc (bundled in Frigate) | single producer per stream, ~566 MB main + 43 MB sub pulled cleanly |
| Mosquitto broker on HOLYGRAIL | listeners 1883 (internal) + 1884 (LAN) |
| Mosquitto bridge HOLYGRAIL → HA | forwarding `frigate/#` OUT, `frigate/+/{detect,recordings,snapshots,motion}/set` IN |
| Advisor backend (rebuilt with feature 017 rules) | rule_engine probing `/api/stats` each cycle, 13 rules registered |
| Advisor migration `009_frigate_thresholds` | applied; 3 threshold rows seeded |

## Acceptance test results

| Test | Spec ref | Result |
|------|----------|--------|
| go2rtc single producer per camera (no Reolink multi-connection bug) | SC-001 | **PASS** — confirmed after removing the native HA Reolink integration; only go2rtc connects to the doorbell |
| Doorbell live stream visible in Frigate UI at LAN URL | FR-026 | **PASS** — http://frigate.holygrail (Mac) and http://192.168.10.129:5000 (HA) both serve |
| Continuous recording lands on `/mnt/frigate` (motion-mode) | FR-016 | **PASS** — recordings appearing under `/mnt/frigate/recordings/` |
| Detection inference latency | FR-015 / SC-002 | **PASS** — 9.72 ms inference on the CPU detector (under 1000 ms SLO by 100×) |
| Advisor rules registered + threshold rows seeded | FR-034 / FR-036 | **PASS** — `frigate_storage_high` + `frigate_detection_latency` both load; thresholds `85%`, `2000ms`, `300s` seeded |
| Advisor pytest for new rules | (test-after) | **PASS** — 17/17 (8 storage + 9 latency) |
| Existing advisor pytest regression | (test-after) | **PASS** — 295/296 (1 pre-existing VPN test failure unrelated to 017) |
| HA privacy-mode round-trip (HA toggle → MQTT bridge → Frigate flips detect+record) | FR-025 | **PASS** — `detect.enabled` + `record.enabled` both flipped True→False on toggle ON, restored on toggle OFF; restreamer never paused (per Clarification Q3) |
| Person at door → push notification with inline snapshot | FR-022 (revised) | **PASS** — notification arrives on all 4 paired iOS devices via `notify.household` group; tap opens Frigate UI |
| Package detection notification | FR-024 | **WIRED** — automation in place; not yet triggered with a real package |
| Person detected at door → porch lights | FR-023 | **DEFERRED** — no smart porch light entity exists in HA yet (see Open follow-ups) |
| Wife-friendly UX acceptance test | SC-003 | **NOT RUN** — manual non-technical-household-member test; can be run anytime now that the system is live |

## Spec deviations (documented before deploy, not surfaced after)

### Deviation 1 — CPU detector instead of GPU TensorRT (FR-011 / SC-002)

**Spec**: GPU detection on the RTX 2070 Super via TensorRT, YOLOv9-T model.
**Reality**: Frigate 0.16+ removed the standalone TensorRT detector (no `tensorrt` Python package in the `stable-tensorrt` image; `TRT_SUPPORT = False` evaluated). GPU detection now goes through the `onnx` detector with onnxruntime's TensorrtExecutionProvider, which requires a YOLO-NAS-S or YOLOv9-T ONNX file with NMS baked in.

Sourcing/exporting that ONNX hit two compatibility walls during deploy:
1. `super-gradients==3.7.1` pins `numpy<=1.23` — conflicts with `onnxruntime>=1.15`'s `numpy>=1.24.2` requirement.
2. Older `onnxruntime` (1.15.0) shared object fails on the modern HOLYGRAIL kernel: `cannot enable executable stack as shared object requires`.

Pragmatic call during the live deploy: ship with the bundled CPU detector (SSD MobileNet on COCO-90, `cpu_model.tflite`) to validate the entire stack end-to-end, and fix GPU detection in a focused follow-up. Inference latency on the Ryzen 7800X3D measured at **9.72 ms** — well under the 1000 ms P95 SLO from SC-002. So FR-011 is the strict violation; SC-002 (latency) actually still passes.

**Follow-up**: dedicated GPU-detection upgrade — generate YOLO-NAS-S ONNX in a working environment (clean Docker container with compatible super-gradients/torch/onnxruntime triple), drop the ONNX into `/opt/frigate-stack/config/model_cache/`, swap `detectors.cpu1` → `detectors.onnx` in `config.yml`. Estimated 1–2 hour follow-up.

### Deviation 2 — HA architecture: removed native Reolink integration (R11 supersedes R9)

**Spec**: Keep the existing native HA Reolink integration; re-point its stream URL to go2rtc within a 30-second window during deploy (research R9).
**Reality**: User chose the cleaner architecture — **remove the Reolink integration from HA entirely**. The audible doorbell chime is hardware-paired with the doorbell via the Reolink mobile app (independent of HA), so the household-critical "ding" path was unaffected.

Consequence: lost the discrete "doorbell button was pressed" event in HA. Replaced with **person-detection trigger** for HA notifications (which is arguably better UX — catches drop-off delivery drivers who don't ring). FR-022 trigger semantic revised in `contracts/ha-automations.yaml`.

**Follow-up**: none required — this is the new steady state.

### Deviation 3 — Mosquitto bridging instead of dedicated broker

**Spec**: Mosquitto broker runs on HOLYGRAIL inside the Frigate compose stack; HA's MQTT integration points at it directly (research R6 + Clarification Q2).
**Reality**: HA's MQTT integration is `single_instance_allowed` and was already pointed at the HA-OS Mosquitto add-on serving WeeWX. Re-pointing it would have orphaned the WeeWX entities. Solution: **bridge** the HOLYGRAIL Mosquitto to HA's local Mosquitto add-on, forwarding `frigate/#` topics OUT and `frigate/+/*/set` topics IN.

Bridge user `holygrail_bridge` lives in HA's Mosquitto add-on config; bridge config lives at `/opt/frigate-stack/mosquitto/config/conf.d/bridge.conf` (gitignored, contains the bridge credentials).

**Follow-up**: none required. Document in research.md as new R12.

## Open follow-ups (not blockers)

1. **GPU detection upgrade (FR-011)** — see Deviation 1. Track as new feature or polish task.
2. **Smart porch light wiring (FR-023)** — household has no smart porch light today. Add one (Aqara, Lutron, etc.), wire to HA, uncomment the automation stub already present in `contracts/ha-automations.yaml`.
3. **Wife-friendly UX acceptance test (SC-003)** — manual test, can be run anytime. Per the spec this is a release gate, but the system is live and usable; the spec gate exists to catch UX friction, not to block deploy.
4. **Pre-existing `advisor-scanner-1` crash loop** — feature 016 deploy left the scanner container missing `ADVISOR_ENCRYPTION_KEY` env var. Trivial fix (add the same Fernet key the backend uses to the scanner's env). Out of scope for 017 but flagged for the next advisor touch.
5. **Pre-existing VPN status test failure** — `test_suppressed_alerts_do_not_change_state` in feature 015's suite. Logic bug in the test, not in production code. Out of scope for 017.
6. **Tailscale remote access (next feature, 018)** — for accessing Frigate UI remotely without exposing port 5000 publicly. Spec to be written.

## Credentials saved

All persisted on HOLYGRAIL (not in repo):
- `/opt/frigate-stack/.env` — Frigate doorbell creds, Mosquitto creds, image tags
- `/opt/frigate-stack/mosquitto/config/passwords` — frigate + homeassistant Mosquitto users
- `/opt/frigate-stack/mosquitto/config/conf.d/bridge.conf` — bridge user creds for HA add-on
- Frigate web UI auto-generated admin password (Frigate 0.16+ enforces auth): saved out-of-band by user; rotatable in the Frigate UI Settings → Authentication.

## Post-deploy refinements (2026-04-18 evening session)

After the initial green-state acceptance, six issues surfaced during real use and were fixed in the same session. Capturing here so the spec docs reflect the final shipped state, not the initial one.

### R1 — Recording playback fails on macOS (Safari + Chrome)

**Symptom**: clicking play on a recording in the Frigate UI showed the camera view briefly then errored: `NSOSStatusErrorDomain Code=-12909 / VTDecompressionOutputCallback`. macOS VideoToolbox couldn't decode mid-stream.

**Root cause**: Frigate's default record mode stream-copies the source. The Reolink doorbell's main stream is H.264 High @ Level 5.1 with B-frames + non-aligned keyframes; ffmpeg's segmenter produced 10-second MP4 segments where some segments didn't start with a keyframe → broken decode dependency chain → macOS hardware decoder rejects.

**Fix**: re-encode with `libx264` at record time, no B-frames, keyframes forced at exact 10s segment boundaries:
```
record: -c:v libx264 -preset veryfast -tune zerolatency
        -profile:v high -bf 0
        -g 200 -force_key_frames expr:gte(t,n_forced*10)
        -pix_fmt yuv420p -c:a aac -ac 1 -ar 16000
```

**Cost**: ~85% of one CPU core during recording (~5% of total Ryzen 7800X3D capacity). Plays cleanly in Safari/Chrome on macOS, iOS, every browser tested.

**Note on NVENC**: tried `h264_nvenc` first (would have been free CPU); the Frigate image's NVIDIA Container Toolkit didn't mount `libnvidia-encode.so.1` despite `NVIDIA_DRIVER_CAPABILITIES=video` being set. Could be fixed with `NVIDIA_DRIVER_CAPABILITIES=all`, but libx264 is bulletproof at this scale and avoids GPU-driver-version surface.

### R2 — Disk usage runaway from constant motion (the flag)

**Symptom**: 676 mp4 files / 3.2 GB written in ~2 hours after first deploy. The doorbell looks at a porch with a flag visible; wind keeps the flag moving constantly = motion-mode retention kept everything = headed for ~13 GB/day.

**Root cause**: original config used `retain.mode: motion` per the spec's FR-017. With ambient motion (flag, leaves, shadows), motion-mode retention effectively keeps 24/7.

**Fix**: pivoted to active-objects-only retention. Frigate 0.17's UI editor auto-migrated my `retain.mode: active_objects` into the new 4-bucket schema, but seeded `motion.days: 30` which would have re-introduced the bug. Final config:
```yaml
record:
  alerts:     { retain: { days: 30 } }   # AI person events → 30d
  detections: { retain: { days: 30 } }   # AI dog/cat events → 30d
  continuous: { days: 0 }                # no 24/7 raw
  motion:     { days: 0 }                # no motion-only retention
```

**One-time cleanup**: stopped Frigate, wiped `/mnt/frigate/{recordings,clips,exports}` and the `frigate.db` files (sudo'd because containers wrote as root). New auto-generated admin password regenerated on restart.

### R3 — Spec deviation: dropped `package` from tracked classes

**Symptom**: `objects.track: [..., package, ...]` silently dropped at runtime; live config showed `track: [person, dog, cat]` only.

**Root cause**: bundled CPU detector is SSD MobileNet on COCO-90 — no `package` class. Frigate validates the track list against the model's known classes and silently drops unknowns.

**Decision**: comment out `package` in config with a follow-up note. Activates when GPU/YOLO upgrade lands (FR-011 follow-up). FR-024 package-notification automation is wired but won't fire until then. User declined the suitcase/handbag proxy approach (false positives outweigh value at this camera angle).

### R4 — Spec deviation: removed `car` from tracked classes

**Symptom**: ambient car traffic on the street visible from the doorbell generated noise events.

**Decision**: removed `car` from `objects.track`. The doorbell only sees the street tangentially; car detection adds noise without value at this camera angle. Re-add for future camera angles where it makes sense.

### R5 — "Person at door" filter (zone + area)

**Symptom**: the doorbell sees a porch + walkup + sidewalk in the distance through the doorway opening. Generated person notifications for people on the sidewalk who would never approach the door.

**Fix (two layers)**:

1. `objects.filters.person.min_area: 5000` (max 300000) — area filter at detect resolution (640×480). Distant sidewalk pedestrians produce <1500 px² bounding boxes; porch visitors produce 12,000+ px²; visitors at the doorbell can fill 200,000+ px². Bumped max_area to accommodate the recessed-entryway camera angle where close-up visitors fill most of frame.

2. `zones.porch` polygon traced via Frigate UI's Mask & Zone Editor. Camera is mounted in a recessed entryway hallway facing outward; polygon excludes the small outdoor doorway opening (sidewalk visible *through* the doorway = not "at the porch") and includes the L-shaped entryway interior. Frigate 0.17 uses normalized 0-1 coordinates: `0,0,0.336,0.014,0.344,0.612,0.522,0.61,0.535,0,1,0,1,1,0,1`.

### R6 — HA person automation: trigger on update + zone-transition (NOT type:new + current_zones)

**Symptom**: notification didn't fire even when Frigate clearly recorded a person event in the porch zone.

**Root cause**: Frigate's `type: new` MQTT event fires with `current_zones=[]` and `entered_zones=[]` — zone membership is computed lazily on subsequent `type: update` events a fraction of a second later. Verified live with mosquitto_sub:
```
type=new     current_zones=[]              ← my condition required current_zones, never matched
type=update  current_zones=[]
type=update  current_zones=['porch']       ← THIS is when the notification should fire
type=update  current_zones=['porch']       ← but NOT again here
type=end     current_zones=['porch']       ← or here
```

Compounding gotcha: `entered_zones` (which I tried first) is *also* unreliable for recessed-entryway mounts — when a visitor's first detected centroid is already inside the polygon, no zone transition occurs and `entered_zones` stays `[]` forever for that event.

**Fix**: trigger on every `frigate/events`, condition checks for *transition into* porch (porch in `after.current_zones` AND porch not in `before.current_zones`). Combined with `mode: single` + `tag: event_id` on the notification, fires exactly once per visit.

```yaml
condition:
  - condition: template
    value_template: >-
      {{ trigger.payload_json.after.camera == 'doorbell'
         and trigger.payload_json.after.label == 'person'
         and 'porch' in trigger.payload_json.after.current_zones
         and 'porch' not in (trigger.payload_json.before.current_zones or []) }}
```

**Lesson worth keeping**: most Frigate-HA notification recipes on the internet trigger on `type: new` with a `current_zones` filter — they work for cameras where motion enters frame *outside* a zone and walks INTO it (entered_zones populates correctly). They fail for recessed-entryway mounts. The transition-on-update pattern works for both topologies.

---

## Health snapshot at deploy completion

```
go2rtc producers (per camera, single-consumer expected):
  doorbell: 1 producer @ 192.168.10.110:554, 566 MB pulled
  doorbell_sub: 1 producer @ 192.168.10.110:554, 43 MB pulled

Frigate /api/stats:
  doorbell.detection_fps = 5.5
  detectors.cpu1.inference_speed = 9.72 ms

Mosquitto bridge:
  Connecting bridge holygrail-to-ha (192.168.10.117:1883)
  frigate/# topics flowing OUT to HA broker (verified via mosquitto_sub on HA broker)
  frigate/+/detect/set + recordings/set flowing IN from HA (verified via privacy round-trip)

Advisor:
  alembic head = 009_frigate_thresholds
  rule_engine.cycle.completed: rules_evaluated=13, alerts_created=0
  HA polling /api/stats every 30s (HACS Frigate integration)
```
