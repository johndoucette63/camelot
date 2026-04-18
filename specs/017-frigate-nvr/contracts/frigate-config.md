# Frigate Config Contract

**Feature**: 017-frigate-nvr
**File**: `/opt/frigate/config/config.yml` on HOLYGRAIL (bind-mounted from `infrastructure/holygrail/frigate/config/config.yml` in the repo)

This document is the **shape contract** for `config.yml` — the structure, required keys, and Phase 2 stub conventions. It is not the literal file (the literal file lives in the infrastructure directory and carries environment-specific values).

---

## Required top-level sections

```yaml
mqtt:               # see data-model.md → MQTT block
detectors:          # see data-model.md → detectors block
model:              # see data-model.md → model block
go2rtc:             # restreamer; streams keyed by name
cameras:            # one entry per camera
record:             # global record defaults (overridable per camera)
snapshots:          # global snapshot defaults
```

## Phase 1 `cameras` entries

```yaml
cameras:
  doorbell:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/doorbell
          roles: [record]
        - path: rtsp://127.0.0.1:8554/doorbell_sub
          roles: [detect]
    detect:
      enabled: true
      width: 640
      height: 640
    objects:
      track: [person, car, dog, cat, package]
    record:
      enabled: true
      retain:
        days: 7
        mode: motion
      events:
        retain:
          default: 30
    snapshots:
      enabled: true
      retain:
        default: 30
```

## Phase 2 stub conventions (FR-031, FR-032)

Every commented Phase 2 stub in both `docker-compose.yml` and `config.yml` MUST:

1. Be clearly labeled `# PHASE 2:` at the top of the block.
2. Reference the Reolink Home Hub by hostname `hub.lan` (to be DHCP-reserved at Phase 2 time), NOT by IP.
3. Use the channel-multiplexed URL pattern `rtsp://frigate:<env.FRIGATE_HUB_PASSWORD>@hub.lan:554/h264Preview_<channel>_<main|sub>` (per R4).
4. Stay valid YAML when uncommented — no placeholder values that break parsing.

Example (in `config.yml`):

```yaml
cameras:
  doorbell:
    # ... Phase 1 entry ...

  # PHASE 2: front solar camera (behind Reolink Home Hub, channel 01)
  # solar_cam_front:
  #   ffmpeg:
  #     inputs:
  #       - path: rtsp://127.0.0.1:8554/solar_cam_front
  #         roles: [record]
  #       - path: rtsp://127.0.0.1:8554/solar_cam_front_sub
  #         roles: [detect]
  #   detect:
  #     enabled: true
  #     width: 640
  #     height: 640
  #   objects:
  #     track: [person, car, dog, cat, package]
  #   record:
  #     enabled: true
  #     retain: { days: 7, mode: motion }
  #     events: { retain: { default: 30 } }
```

And in `go2rtc.streams` the corresponding stubs point at the hub IP with the channel number:

```yaml
go2rtc:
  streams:
    doorbell:
      - rtsp://frigate:${FRIGATE_DOORBELL_PASSWORD}@doorbell.lan:554/h264Preview_01_main
    doorbell_sub:
      - rtsp://frigate:${FRIGATE_DOORBELL_PASSWORD}@doorbell.lan:554/h264Preview_01_sub
    # PHASE 2: hub-backed cameras share hub.lan and differ only by channel
    # solar_cam_front:
    #   - rtsp://frigate:${FRIGATE_HUB_PASSWORD}@hub.lan:554/h264Preview_01_main
    # solar_cam_front_sub:
    #   - rtsp://frigate:${FRIGATE_HUB_PASSWORD}@hub.lan:554/h264Preview_01_sub
    # solar_cam_side:
    #   - rtsp://frigate:${FRIGATE_HUB_PASSWORD}@hub.lan:554/h264Preview_02_main
    # solar_cam_side_sub:
    #   - rtsp://frigate:${FRIGATE_HUB_PASSWORD}@hub.lan:554/h264Preview_02_sub
```

## Retention tuning

Retention is the per-camera tunable surface (FR-017). Admins can edit `retain.days` and `events.retain.default` inside the respective camera block without re-running `/speckit.plan`. The Advisor disk-fill rule (FR-034) is the backstop if tuning drives disk usage toward overflow.

## Secrets

All passwords and tokens MUST come from `.env` (gitignored), interpolated by Docker Compose at container start. `config.yml` MUST NOT contain literal passwords. Reference pattern: `${FRIGATE_DOORBELL_PASSWORD}`, `${FRIGATE_MQTT_PASSWORD}`.
