# Quickstart — Frigate NVR (feature 017)

**Target**: HOLYGRAIL (`192.168.10.129`) + existing Home Assistant host + Reolink Video Doorbell WiFi.

These steps are executed once, in order, to stand up the feature end-to-end and run the acceptance tests that gate release.

---

## Pre-flight checklist

- [ ] HOLYGRAIL Ubuntu 24.04, Docker, NVIDIA Container Toolkit all healthy (`nvidia-smi` works; `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi` succeeds).
- [ ] The existing Ollama stack is running and stable (so we don't mistake Ollama-induced instability for a Frigate problem).
- [ ] A dedicated drive (≥2 TB recommended) is installed in HOLYGRAIL, visible under `lsblk`, and has no data you care about.
- [ ] Reolink Video Doorbell WiFi is online and reachable on the LAN.
- [ ] The native Home Assistant Reolink integration is currently working against the doorbell (this is the baseline we're migrating).
- [ ] Admin has console access to the router to set a DHCP reservation.

## Step 1 — Router: reserve the doorbell's IP

1. On the router admin UI, add a static DHCP reservation for the doorbell's MAC.
2. Assign a stable hostname `doorbell.lan` (or add an A record in Pi-hole → `doorbell.lan → <reserved IP>`).
3. Verify: `ping doorbell.lan` from HOLYGRAIL resolves and replies.

## Step 2 — Doorbell: enable RTSP/ONVIF and set a safe password

In the Reolink mobile app, for the doorbell:

1. Settings → Network → Advanced → enable RTSP and ONVIF.
2. Settings → Camera → Admin Password → set a password using ONLY these characters: `a-z A-Z 0-9 @$*~_-+=!?.,:;'()[]` (FR-009).
3. Note the password; it will go in `.env` as `FRIGATE_DOORBELL_PASSWORD`.
4. Verify RTSP manually from HOLYGRAIL: `ffprobe rtsp://<user>:<pass>@doorbell.lan:554/h264Preview_01_main` should return stream info.

## Step 3 — HOLYGRAIL: prepare `/mnt/frigate`

```bash
# Identify the dedicated drive. DO NOT continue if wrong drive.
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT

# Replace /dev/sdX with the correct drive. Irreversible — double-check.
sudo mkfs.ext4 -L frigate /dev/sdX1
sudo mkdir -p /mnt/frigate
echo 'LABEL=frigate /mnt/frigate ext4 defaults,noatime,nofail,x-systemd.device-timeout=10s 0 2' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount /mnt/frigate
sudo chown 1000:1000 /mnt/frigate
df -h /mnt/frigate   # expect the full drive size
```

## Step 4 — Deploy the Frigate stack

From the Mac (per the project's non-git deploy pattern for HOLYGRAIL services):

```bash
# Sync the stack directory to HOLYGRAIL.
rsync -av --delete infrastructure/holygrail/frigate/ holygrail:/opt/frigate-stack/

# On HOLYGRAIL:
ssh holygrail <<'EOF'
  cd /opt/frigate-stack
  cp .env.example .env
  # Edit .env — set FRIGATE_DOORBELL_PASSWORD, FRIGATE_MQTT_PASSWORD, HA_MQTT_PASSWORD.
  # (Open in $EDITOR, fill in, save.)
  docker compose pull
  docker compose up -d
  sleep 15
  docker compose logs --tail=50 frigate
EOF
```

Expected: Frigate logs show go2rtc connecting to the doorbell, TensorRT model generating/loading (first boot takes 3–5 minutes on an RTX 2070 Super), and `frigate/available` published as `online`.

## Step 5 — Switch the HA Reolink integration onto go2rtc

**Time-critical — execute within ~30 seconds** (per R9 in research).

1. In HA, Settings → Devices & Services → Reolink → find the doorbell camera.
2. Change its stream source to `rtsp://holygrail:8554/doorbell` (go2rtc's path).
3. Save; HA will reconnect.
4. Verify exactly one upstream from go2rtc: `ssh holygrail 'docker exec frigate curl -s http://localhost:1984/api/streams'` should show `consumers: 2+` but only one `producer`.

## Step 6 — Install the HACS Frigate integration in HA

1. In HA, HACS → Integrations → Frigate → install.
2. Restart HA.
3. Add the Frigate integration via Settings → Devices & Services → Add Integration → Frigate.
4. MQTT broker: `holygrail:1884` with user `homeassistant` and the `HA_MQTT_PASSWORD` from `.env`.
5. Frigate API URL: `http://holygrail:5000`.
6. Verify HA now shows `binary_sensor.doorbell_person`, `binary_sensor.doorbell_package`, etc.

## Step 7 — Wire up the HA automations

Copy the contents of `specs/017-frigate-nvr/contracts/ha-automations.yaml` into the HA config (merge `input_boolean`, add automations to `automations.yaml`). Reload automations.

Verify:

- Toggle `input_boolean.frigate_privacy_mode` ON → `frigate/doorbell/detect/set` and `frigate/doorbell/recordings/set` receive `OFF` (check with `mosquitto_sub -h holygrail -p 1884 -u homeassistant -P <pass> -t 'frigate/#' -v`).

## Step 8 — Ship the Advisor rules

From the Mac:

```bash
# Deploy Advisor per project pattern (no git pull on HOLYGRAIL — memory: advisor deploy path).
bash scripts/deploy-advisor.sh
# Run migration 009 to seed thresholds.
ssh holygrail 'docker exec advisor-backend alembic upgrade head'
# Verify the two rows exist.
ssh holygrail "docker exec advisor-postgres psql -U advisor -d advisor -c \
  \"SELECT rule_name, field_name, value FROM alert_thresholds WHERE rule_name LIKE 'frigate_%';\""
```

Expected output:

```text
        rule_name          |  field_name  | value
---------------------------+--------------+-------
 frigate_storage_high      | fill_percent |    85
 frigate_detection_latency | p95_ms       |  2000
```

Run the Advisor rule tests:

```bash
ssh holygrail 'docker exec advisor-backend pytest tests/rules/test_frigate_storage_high.py tests/rules/test_frigate_detection_latency.py -q'
```

## Step 9 — Commit the Phase 2 expansion checklist

Ensure `docs/frigate-phase2-expansion.md` exists in the repo and covers (per FR-033):

- [ ] Reolink Home Hub onboarding steps (DHCP reservation, password set to safe charset, RTSP/ONVIF enabled on the hub).
- [ ] Uncommenting the Phase 2 stubs in `config.yml` and `docker-compose.yml`.
- [ ] Channel assignment convention (`01`, `02`, …) per camera behind the hub.
- [ ] Validation: `docker compose restart frigate`, check go2rtc UI, confirm Advisor does not alert.
- [ ] HA integration picks up new camera entities automatically.

---

## Acceptance tests (the release gates)

### US-1 — Doorbell + recording stability (SC-001)

- [ ] Ring the doorbell 10× in 10 minutes.
- [ ] Frigate event feed shows at least 1 event per ring.
- [ ] Restreamer shows zero frame drops; doorbell never reboots (Reolink app "last seen" is continuous).
- [ ] Continuous recording file exists for the full 10-minute window on `/mnt/frigate`.

### US-2 — GPU detection (SC-002, SC-007)

- [ ] `nvidia-smi` shows Frigate on the GPU during detection.
- [ ] Walk into frame → `person` event within 1s (eyeball the event-log timestamp vs wall clock).
- [ ] Place a package on the porch → `package` event within 3s.
- [ ] Run an Ollama chat completion concurrently; detection still lands, possibly with higher latency; no detector crash in logs.

### US-3 — Wife-friendly review UX (SC-003) — RELEASE GATE

- [ ] Non-technical household member, first time seeing the system, given only the URL `http://holygrail:5000`.
- [ ] Task A: "What's happened in the last 24 hours?" — must complete unassisted.
- [ ] Task B: "Show me everything from yesterday afternoon." — must complete unassisted.
- [ ] Task C: "Was there a package delivery this week?" — must complete unassisted.
- [ ] All three within 3 minutes. Observe and note friction; don't coach.

### US-4 — Home Assistant automations (SC-004)

- [ ] Press the doorbell → phone notification with snapshot + UI link within 5s.
- [ ] Walk into frame → porch lights on within 3s.
- [ ] Leave a package → notification with clip link arrives.
- [ ] Toggle privacy mode ON → subsequent motion produces no event clips and no HA entity state change until toggled OFF.

### US-5 — Phase 2 readiness (SC-008)

- [ ] `docs/frigate-phase2-expansion.md` exists, is self-service, and has been spot-checked by reading it end-to-end without reference to `spec.md` or the F6.2 source doc.

### Observability (FR-034/36)

- [ ] Simulate a disk-fill spike (drop a large file into `/mnt/frigate` so fill ≥85% briefly) → Advisor `frigate_storage_high` alert fires → HA receives notification.
- [ ] (Optional, best-effort) Run a sustained heavy Ollama load and observe — if `frigate_detection_latency` fires, capture the data; otherwise mark as "did not trigger under test" and keep the rule armed.

### Reboot resilience (SC-005)

- [ ] Reboot HOLYGRAIL.
- [ ] Within 2 minutes of the host coming back, Frigate UI is reachable and doorbell is live.
- [ ] Advisor rules resume without manual intervention.

---

## Post-deploy — save to memory

Per the project's memory preferences (`feedback_quickstart_after_implement.md`), running this quickstart is the final validation step. Once complete, update `MEMORY.md` with a brief `project_` entry if anything surprising turned up during deploy (e.g., detection latency was worse than expected, or a particular doorbell password character caused a regression) — otherwise leave memory untouched.
