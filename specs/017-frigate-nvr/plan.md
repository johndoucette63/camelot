# Implementation Plan: Frigate NVR — Local AI Camera Surveillance

**Branch**: `017-frigate-nvr` | **Date**: 2026-04-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/017-frigate-nvr/spec.md`

## Summary

Deploy a local, GPU-accelerated NVR stack on HOLYGRAIL that pulls the Reolink Video Doorbell WiFi through a single go2rtc upstream connection, runs YOLOv9-TensorRT object detection on the RTX 2070 Super, records 24/7 footage plus event clips to a dedicated drive, and integrates with Home Assistant via a Mosquitto MQTT broker living in the same compose stack. Observability is delivered by extending the Camelot Advisor with two new rules (disk-fill on `/mnt/frigate`, sustained detection-latency breach) whose thresholds live in the existing `alert_thresholds` table so they can be tuned without code changes. Phase 1 targets exactly one camera; compose + Frigate config carry commented stubs for the Phase 2 Reolink Home Hub expansion, and a self-service expansion checklist ships in `docs/`.

## Technical Context

**Language/Version**: Docker Compose YAML (configs); Python 3.12 for the Advisor rule extensions (existing project Python version)
**Primary Dependencies**: `ghcr.io/blakeblackshear/frigate:stable-tensorrt` (pinned to a specific tag; bundles go2rtc), `eclipse-mosquitto:2` (pinned), NVIDIA Container Toolkit (already installed per Phase 1), YOLOv9 TensorRT model (generated at first boot), HACS Frigate integration (installed inside HA)
**Storage**:
- Dedicated drive/partition mounted at `/mnt/frigate` on HOLYGRAIL for clips + continuous recordings
- Frigate config bind-mounted at `/opt/frigate/config` (config.yml + tokenized model cache)
- Mosquitto persistence in a docker-managed volume (`frigate_mosquitto_data`)
- No new Advisor DB tables — new threshold rows are seeded into the existing `alert_thresholds` table via data-only migration or an idempotent startup seeder

**Testing**:
- pytest for the two new Advisor rules (integration-style, hitting a real Postgres test DB per existing pattern)
- Manual acceptance test with a non-technical household member (UX gate per US-3)
- Manual 14-day burn-in against the Reolink multi-connection bug (per SC-001)

**Target Platform**: HOLYGRAIL (Ubuntu 24.04, x86_64, RTX 2070 Super 8GB, CUDA 12.8, Driver 570.211.01). Camera: Reolink Video Doorbell WiFi on `192.168.10.0/24` with static DHCP reservation.

**Project Type**: Infrastructure deployment (one new docker-compose stack on HOLYGRAIL) + Advisor rule extension (two new rule files + seeded thresholds). No new frontend or API work beyond what Frigate ships natively.

**Performance Goals**:
- P95 motion-to-event-in-UI latency < 1s under non-contention (SC-002)
- P95 doorbell-press to phone notification < 5s (SC-004)
- Stack up within 2 minutes of HOLYGRAIL boot (SC-005)

**Constraints**:
- Fully local — no cloud calls (Constitution I)
- GPU shared with Ollama; detector must remain on GPU, no silent CPU fallback (SC-007)
- Restreamer MUST be the only process connected to the doorbell's RTSP endpoint (FR-010) — the existing native HA Reolink integration will continue to consume the doorbell, so it must be repointed at go2rtc as part of this feature
- Reolink-safe password character set enforced at doorbell setup time (FR-009)
- `/mnt/frigate` must never exceed 90% fill over a 30-day window (SC-006)

**Scale/Scope**:
- 1 camera in Phase 1 (doorbell)
- 30-day event retention, 7-day continuous-footage retention (default, per-camera tunable)
- Phase 2 stubs for 2–4 hub-backed solar cameras behind a Reolink Home Hub (out-of-scope for this feature, but the config shape must not need a rewrite later)

## Constitution Check

Evaluated against `.specify/memory/constitution.md` v1.1.0.

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Local-First | ✅ Pass | All services run on HOLYGRAIL; no cloud dependencies. MQTT broker is in-stack. LAN-only notifications (FR-024a). |
| II. Simplicity & Pragmatism | ✅ Pass | One compose stack. Reuses existing Advisor threshold table for FR-034/35/36/37 (no new tables, no new alerting pipeline). No GPU scheduler. No automatic CPU/Coral failover. Phase 2 is deferred. |
| III. Containerized Everything | ✅ Pass | Frigate + Mosquitto in a single compose file at `infrastructure/holygrail/frigate/docker-compose.yml`. `restart: unless-stopped`. GPU via `nvidia-container-toolkit`. Secrets (doorbell password, MQTT creds) in a gitignored `.env`. |
| IV. Test-After | ✅ Pass | Two new Advisor rules get pytest integration tests after implementation. UX validation is a manual acceptance test (constitution does not require automated tests for infrastructure deployments). No TDD. |
| V. Observability | ✅ Pass | Frigate exposes `/api/stats` + Prometheus metrics (health endpoint equivalent). Container logs are JSON-structured for Docker log collection. Advisor rules FR-034/FR-036 raise alerts for disk and detection-latency breaches through the existing HA notification sink. Grafana dashboard is a nice-to-have (documented but not gated on). |

**No violations — proceed to Phase 0.**

### Post-Design Re-Check (after Phase 1)

Re-evaluated after generating `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`. All five principles still pass:

- **Local-First**: MQTT broker lives in-stack (R6), LAN-only notifications (FR-024a), latency rule polls an on-host endpoint (R7). No new cloud surface introduced.
- **Simplicity**: Design stayed with bundled go2rtc (R3), reused `alert_thresholds` table (no schema change), no MPS/MIG scheduler (R8), no automatic CPU failover (per spec clarification Q5). Phase 2 is config stubs only.
- **Containerized**: Two containers (`frigate`, `mosquitto`) in one compose stack, pinned images, `.env` secrets, `restart: unless-stopped`.
- **Test-After**: Two pytest files planned for the new Advisor rules, to be written after the rule code lands. UX gate is a manual acceptance test in quickstart.
- **Observability**: FR-034/35/36/37 realize the Observability principle directly — disk and latency both alert through the existing HA notification sink.

No Complexity Tracking entries required.

### Constitution V nuances for this feature

- **`/health` equivalency**: Frigate's native `/api/stats` endpoint is treated as the liveness probe that satisfies Constitution V's "all services MUST expose `/health`" requirement. Precedent: the existing Ollama stack uses `/api/tags` as its liveness probe (not a custom `/health`) and is accepted as compliant. The Advisor's FR-036 latency rule depends on `/api/stats` specifically, so introducing a separate `/health` shim would add surface without value. Mosquitto liveness is covered by the MQTT-level connectivity check the HACS Frigate integration already performs on its side; no additional probe is needed at the infrastructure layer.
- **Grafana dashboard (task T044)**: the dashboard panel is deliberately scoped as best-effort rather than a hard gate. Rationale under Constitution II (Simplicity): the FR-034/35/36/37 Advisor alerts already surface the two metrics that matter (storage fill, detection latency) through the same notification path used by every other Camelot service. A Grafana panel adds visual affordance, not alerting capability. If T044 slips, no observability capability is lost — only dashboard convenience.

## Project Structure

### Documentation (this feature)

```text
specs/017-frigate-nvr/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions on Frigate tag, model pick, drive, MQTT, metrics source
├── data-model.md        # Phase 1 — advisor threshold seeds + frigate config entities
├── quickstart.md        # Phase 1 — step-by-step to bring the stack up + acceptance-test walkthrough
├── contracts/           # Phase 1 — MQTT topic contract + HA automation YAML contracts
│   ├── mqtt-topics.md
│   ├── ha-automations.yaml
│   └── frigate-config.md
└── tasks.md             # Phase 2 — generated by /speckit.tasks (NOT by this command)
```

### Source Code (repository root)

```text
infrastructure/holygrail/frigate/
├── docker-compose.yml                  # Frigate + Mosquitto, pinned images, GPU runtime, restart policy
├── .env.example                        # Placeholder for FRIGATE_RTSP_PASSWORD, MQTT_USER, MQTT_PASS
├── config/
│   ├── config.yml                      # Frigate config: go2rtc stream, detector, records, snapshots, mqtt
│   └── README.md                       # What to edit, what not to edit
├── mosquitto/
│   └── config/
│       ├── mosquitto.conf              # Listeners (1883 LAN, 1884 loopback for Frigate)
│       └── passwords.example           # User seed for frigate + homeassistant clients
└── README.md                           # Stack overview + operational runbook

advisor/backend/app/services/rules/
├── frigate_storage_high.py             # FR-034/35 — disk-fill alert on /mnt/frigate
└── frigate_detection_latency.py        # FR-036/37 — P95 latency sustained-breach alert

advisor/backend/migrations/versions/
└── 009_frigate_thresholds.py           # Data-only migration: seed threshold rows for the two new rules

advisor/backend/tests/rules/
├── test_frigate_storage_high.py
└── test_frigate_detection_latency.py

docs/
├── F6.2-frigate-nvr.md                 # Pre-existing source feature doc (unchanged)
└── frigate-phase2-expansion.md         # NEW — self-service checklist for FR-033
```

**Structure Decision**: Two real-source locations.

1. **`infrastructure/holygrail/frigate/`** for the docker-compose stack. This matches the existing `infrastructure/holygrail/{ollama,plex,monitoring,traefik}/` convention — one directory per service stack on HOLYGRAIL, one compose file per stack, config in-tree, secrets in a gitignored `.env`. Mosquitto lives inside the Frigate stack rather than getting its own top-level directory because its only purpose here is bridging Frigate to HA (per Clarification Q2).

2. **`advisor/backend/app/services/rules/`** for the two new Advisor rules. This matches the existing `disk_high.py`, `service_down.py`, `ollama_unavailable.py` pattern. The rules reuse the existing `alert_thresholds` table via migration `009_frigate_thresholds.py` — a pure data migration that seeds rows, no schema change (per Constitution II Simplicity and spec clarifications).

A new `docs/frigate-phase2-expansion.md` is the self-service checklist required by FR-033; it is intentionally separate from this spec so a future admin can follow it in isolation.

## Complexity Tracking

No constitution violations — table intentionally empty.
