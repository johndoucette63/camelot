# Frigate Phase 2 Expansion Checklist

**Purpose**: self-service runbook for onboarding cameras behind the Reolink Home Hub to the existing Frigate NVR stack on HOLYGRAIL. Follow this checklist end-to-end without reading anything else — if a step is unclear, the checklist is the bug; fix it here.

**Audience**: you, six months from now, with zero memory of the Phase 1 deploy.

**Scope**: adding 1–N battery/solar cameras (Reolink Altas or similar) that stream through a Reolink Home Hub. Each new camera is one channel on the hub. The stack, detector, MQTT broker, and Home Assistant integration already exist — this is a config-only expansion.

---

## Prerequisites

- [ ] Phase 1 is deployed and healthy: `http://frigate.holygrail` shows the doorbell, HA receives events, the Camelot Advisor is green.
- [ ] The Reolink Home Hub is physically set up and connected to your LAN.
- [ ] Each new camera is paired with the Hub per the Reolink app (Hub Settings → Add Camera).
- [ ] Each camera is showing live in the Reolink app through the Hub.

## Step 1 — Hub: pick a stable address

- [ ] On the router admin UI: add a DHCP reservation for the Hub's MAC.
- [ ] On Pi-hole (`192.168.10.150`): add local DNS entry `hub.lan → <reserved IP>`.
- [ ] From HOLYGRAIL, verify: `ping hub.lan` resolves and replies.

## Step 2 — Hub: enable RTSP/ONVIF + set a safe password

- [ ] In the Reolink app → Hub → Settings → Network → Advanced → enable **RTSP** and **ONVIF**.
- [ ] Hub admin password MUST use only the Reolink-safe character set: `a-z A-Z 0-9 @$*~_-+=!?.,:;'()[]`. Any other character silently breaks RTSP encoding (same firmware bug as the doorbell in Phase 1).
- [ ] Record the Hub password; it goes in `.env` as `FRIGATE_HUB_PASSWORD` and `FRIGATE_HUB_USER` (typically `admin`).

## Step 3 — Map cameras to channels

Reolink hubs multiplex camera streams by channel number (`01`, `02`, `03`, ...). Before editing config, decide which camera is on which channel and write it down. Channels are assigned in the order cameras were paired.

- [ ] Run `ffprobe rtsp://admin:<pass>@hub.lan:554/h264Preview_01_main` etc. to confirm which physical camera each channel maps to.
- [ ] Record the channel → camera mapping, e.g.:

  ```text
  01 -> solar_cam_front
  02 -> solar_cam_side
  03 -> solar_cam_back
  ```

## Step 4 — Update secrets on HOLYGRAIL

- [ ] SSH to HOLYGRAIL, edit `/opt/frigate-stack/.env`:
  - [ ] Uncomment `FRIGATE_HUB_USER=admin`.
  - [ ] Uncomment `FRIGATE_HUB_PASSWORD=` and paste the Hub password.

## Step 5 — Uncomment the Phase 2 stubs

In the repo on the Mac, edit `infrastructure/holygrail/frigate/config/config.yml`:

- [ ] Uncomment the Phase 2 `go2rtc.streams.solar_cam_*` entries you need (one main + one sub per camera).
- [ ] Uncomment the Phase 2 `cameras.solar_cam_*` blocks for the same cameras.
- [ ] Replace placeholder camera names with the names you chose in Step 3.
- [ ] Adjust the `h264Preview_<channel>_*` number for each entry to match your channel mapping.
- [ ] Save. Do NOT edit the doorbell entries.

Also edit `infrastructure/holygrail/frigate/docker-compose.yml`:

- [ ] Uncomment the Phase 2 `FRIGATE_HUB_USER` / `FRIGATE_HUB_PASSWORD` environment lines under the `frigate` service.

## Step 6 — Deploy

From the Mac:

- [ ] `rsync -av --delete infrastructure/holygrail/frigate/ holygrail:/opt/frigate-stack/`
- [ ] `ssh holygrail 'cd /opt/frigate-stack && docker compose up -d'`
- [ ] Watch the Frigate logs: `ssh holygrail 'docker logs -f frigate'`. Expect go2rtc to connect each new stream. No `connection refused`, no `401 Unauthorized`.

## Step 7 — Verify in the Frigate web UI

- [ ] Open `http://frigate.holygrail`. Each new camera should have its own tile on the landing dashboard.
- [ ] Click each camera; live stream plays; motion events appear over the next 10 minutes.

## Step 8 — HA picks up the new entities automatically

- [ ] In Home Assistant → Settings → Devices & Services → Frigate → **Reload**.
- [ ] New `binary_sensor.<camera>_person`, `<camera>_package`, `<camera>_visitor` entities appear.
- [ ] If you want porch-light / notification automations for the new cameras, clone the Phase 1 automation patterns from `specs/017-frigate-nvr/contracts/ha-automations.yaml` and adjust `frigate/<camera>/*` topic names.

## Step 9 — Adjust the storage threshold if needed

Adding cameras multiplies continuous-recording footprint. If the added cameras push storage above the 85% threshold, the existing `frigate_storage_high` Advisor rule will fire — that's the correct behavior. Options:

- [ ] Accept it and let Frigate retention prune naturally (once `record.retain.days` of the new cameras trickles in, disk usage stabilizes).
- [ ] Reduce `retain.days` per new camera in `config.yml` (solar/motion-activated cameras usually don't need 7 days of continuous recording — consider 2–3 days or `record.retain.mode: motion` only).
- [ ] Add storage: install a larger drive and remount at `/mnt/frigate`, OR bump the `frigate_storage_fill_percent` threshold in the Advisor thresholds UI.

## Step 10 — Commit

- [ ] `git add infrastructure/holygrail/frigate/config/config.yml infrastructure/holygrail/frigate/docker-compose.yml`
- [ ] Commit with a message referencing the new cameras: `feat(frigate): onboard <camera names> via Reolink Home Hub`.

---

## Troubleshooting quick reference

| Symptom | Check |
|---------|-------|
| Stream shows `401 Unauthorized` in Frigate logs | Hub password has an unsafe character; reset per Step 2. |
| Stream connects but no frames | Wrong channel number in `h264Preview_<channel>_*`. Re-run the `ffprobe` from Step 3. |
| Camera appears offline in the Reolink app | Physical pairing issue — fix in the app before revisiting Frigate. |
| Doorbell goes offline after expansion | Immediately back out your `config.yml` changes: `git checkout` the file, redeploy. This did not happen in testing, but the Reolink multi-connection bug is touchy. |
| Advisor fires `frigate_storage_high` repeatedly | Step 9 options apply. |

## Out of scope (still)

- Remote access via Tailscale — separate feature; do not touch the Frigate stack for this.
- iOS viewer apps (Viewu, etc.) — nice-to-have, not a deploy blocker. If desired, they connect to `rtsp://holygrail:8554/<camera>` (go2rtc) and they count as a consumer — but unlike the doorbell, hub-backed streams are not subject to the Reolink multi-connection bug, so adding one more consumer is safe.
