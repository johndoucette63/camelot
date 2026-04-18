# MQTT Topic Contract: Frigate ↔ Home Assistant

**Feature**: 017-frigate-nvr — Phase 1 (doorbell only)
**Broker**: Mosquitto in the Frigate compose stack on HOLYGRAIL

All topics use Frigate's default `frigate/` prefix (no custom `topic_prefix` override). This is the contract the HACS Frigate integration and HA automations rely on; it MUST NOT drift.

---

## Topics Frigate publishes (read-only for HA)

| Topic | Payload | Frequency | Used by |
|-------|---------|-----------|---------|
| `frigate/available` | `online` / `offline` | LWT + startup | HA availability sensor |
| `frigate/stats` | JSON stats (per-camera FPS, detection inference, CPU, GPU, storage) | every ~60s | Advisor rules FR-034 / FR-036 polling is HTTP not MQTT, but HA Frigate integration uses this for diagnostics |
| `frigate/events` | JSON (event start/update/end with `camera`, `label`, `id`, `box`, `snapshot_path`, `clip_url`) | per event lifecycle | HA automations (FR-022, FR-024); event history |
| `frigate/doorbell/person` | `0` / `1` | on detection boundary | HA porch-light automation (FR-023) |
| `frigate/doorbell/package` | `0` / `1` | on detection boundary | HA package-notification automation (FR-024) |
| `frigate/doorbell/visitor` | `0` / `1` | on detection boundary | HA visitor sensor |

The `doorbell` segment is the camera name from `config.yml`. Phase 2 cameras will publish under the same shape: `frigate/<camera>/<label>`.

## Topics HA publishes / Frigate subscribes (write)

| Topic | Payload | Purpose |
|-------|---------|---------|
| `frigate/doorbell/detect/set` | `ON` / `OFF` | Privacy mode — pause detection (R10) |
| `frigate/doorbell/recordings/set` | `ON` / `OFF` | Privacy mode — pause recording (R10) |
| `frigate/doorbell/snapshots/set` | `ON` / `OFF` | (Optional) pause snapshots during privacy |
| `frigate/doorbell/motion/set` | `ON` / `OFF` | (Reserved) runtime toggles |

Privacy mode toggles `detect/set` and `recordings/set` together from a single HA switch entity (see `ha-automations.yaml`). The restreamer (`go2rtc`) is **never** paused via any topic — per FR-025 clarification.

## Doorbell-press event topic

Reolink doorbells emit a button-press event via ONVIF, surfaced into Frigate, which republishes on:

| Topic | Payload | Used by |
|-------|---------|---------|
| `frigate/doorbell/visitor` | `1` (press) → `0` (released) | HA doorbell-press notification automation (FR-022) |

If the HACS Frigate integration version in use does not surface this topic natively, the fallback is to have HA subscribe to the doorbell's ONVIF event via the existing Reolink integration — both paths are valid, and the spec only requires that a doorbell press produces a phone notification within 5s (SC-004), not the specific path it takes.

---

## QoS and retention

- All topics: QoS 0 (at-most-once). Frigate/HACS integration defaults.
- Retained messages: Frigate retains `frigate/available` and the `set` topics. Event topics are NOT retained (avoid phantom events on HA restart).

## Client identities

| Client ID | Auth user | Host | Access |
|-----------|-----------|------|--------|
| `frigate-holygrail` | `frigate` | HOLYGRAIL, internal compose network | publish + subscribe on `frigate/#` |
| `homeassistant` | `homeassistant` | HA host, LAN | subscribe on `frigate/#`; publish on `frigate/+/{detect,recordings,snapshots,motion}/set` only |

Mosquitto ACL (`/mosquitto/config/acl`) enforces this split — see R6 in research.
