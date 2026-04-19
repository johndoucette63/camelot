# Feature 019 — Garage Camera

**Branch**: `019-garage-camera` (created from master at `fe21ff3`, fast-forward merged back at `11daf04`)
**Status**: Shipped 2026-04-19
**Scope**: Light enough to skip the full spec-kit ceremony — config-only addition to the existing 017 Frigate stack on HOLYGRAIL. This file is a retrospective in lieu of spec/plan/tasks.

## Why

The Frigate Phase 1 deploy (017) onboarded the doorbell only. The household has an existing Wansview garage camera at `192.168.10.128` already wired into HA as a generic `camera.192_168_10_128` entity — but with none of the Frigate benefits (recordings, scrub timeline, dashboard tab). User wanted to fold it into the same Frigate stack so the Advanced Camera Card dashboard has both cameras side-by-side.

Constraint: **no AI detection, no notifications**. Garage is for after-the-fact security review, not real-time alerts. The audible chime and HA-driven automations stay doorbell-only.

## Commits (chronological)

| SHA | Title | Why |
|-----|-------|-----|
| `11daf04` | `feat(frigate): add Wansview garage camera (live + 24/7 record, no detection)` | Bring the camera into the stack. RTSP path `/live/ch0` was non-standard for Wansview (the usual `/live/ch00_0`, `/h264`, etc. all 404'd) — user pulled the working URL from HA's existing camera entity. Initial setup was 24/7 continuous recording at 30 days. |
| `0500cc8` | `fix(frigate): garage to motion-only retention (no 24/7 continuous)` | User pivot when the disk-math became real (24/7 1080p20 ≈ 1.6 TB for 30 days, drive is 787 GB). Switched `record.continuous.days` 30→0 and `record.motion.days` 0→30. Live view unaffected (go2rtc serves that independently). Storage estimate dropped to ~50–80 GB for 30 days. |
| `4f0b249` | `fix(frigate): garage to stream-copy recording (93% → 8% CPU)` | Frigate UI flagged "high FFmpeg CPU usage (93%)" on the garage. The libx264 re-encode we copied from the doorbell config (originally added to fix Reolink B-frame playback issues) wasn't necessary for Wansview — its H.264 stream is cleaner. Switched to Frigate's `preset-record-generic-audio-aac` (video stream-copy + AAC audio). CPU dropped from 93% to 8%. |
| `5ebb8e8` | `fix(frigate): force RTSP-over-TCP for garage (Wansview UDP packet loss)` | Live view + recordings showed horizontal banding + magenta color shifts. ffprobe comparison: UDP transport produced ~1000 macroblock errors per P-frame, TCP was clean. Added `?rtsp_transport=tcp` to the go2rtc URL. Required a follow-up camera **power-cycle** for the change to take effect (camera held stale UDP session state — see `~/.claude/projects/-Users-jd-Code-camelot/memory/reference_rtsp_camera_transport_change.md`). |

## What also happened (no commit, but part of 019)

- **Pi-hole DNS** added: `garage.lan → 192.168.10.128` (in `pihole.toml` on the media server, not in this repo)
- **`.env`** on HOLYGRAIL got `FRIGATE_GARAGE_USER=admin` + `FRIGATE_GARAGE_PASSWORD=subterra` (gitignored)
- **HA dashboard card** updated to add the garage tab — `camera.192_168_10_128` swapped for the Frigate-managed `camera.garage`
- **Old corrupted recordings** (~30 GB / 4,601 mp4 files written during the UDP-glitch period) wiped after the TCP fix landed

## Lessons worth keeping

1. **Wansview RTSP path is non-standard** — when probing an unfamiliar camera, pulling the URL from HA's existing camera entity is faster than guessing.
2. **Stream-copy is fine for cameras with clean H.264** — the libx264 re-encode was overkill for the garage. Reserve re-encoding for cameras with pathological streams (Reolink doorbell B-frame issues).
3. **RTSP transport changes need a camera power-cycle** — go2rtc/ffmpeg URL change alone isn't enough if the camera held a UDP session. Documented as a project memory.
4. **Live view is independent of recording config** — `record.continuous.days: 0` doesn't disable live; go2rtc serves the live stream regardless of retention.

## Final state

```yaml
# infrastructure/holygrail/frigate/config/config.yml — relevant garage block
go2rtc:
  streams:
    garage:
      - rtsp://{FRIGATE_GARAGE_USER}:{FRIGATE_GARAGE_PASSWORD}@garage.lan:554/live/ch0?rtsp_transport=tcp

cameras:
  garage:
    ffmpeg:
      output_args:
        record: preset-record-generic-audio-aac
      inputs:
        - path: rtsp://127.0.0.1:8554/garage
          roles: [record]
    detect:
      enabled: false
    record:
      enabled: true
      continuous: { days: 0 }
      motion:     { days: 30 }
      alerts:     { retain: { days: 30 } }
      detections: { retain: { days: 30 } }
    snapshots:
      enabled: true
      retain: { default: 30 }
```

Source bitrate ~5 Mbps stream-copied → ~50 GB/30 days at typical motion rates. ~8% CPU per stream. Live view via go2rtc WebRTC.
