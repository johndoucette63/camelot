# Implementation Plan: Indexers & Quality Optimization

**Branch**: `014-indexers-quality` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/Users/jd/Code/camelot/specs/014-indexers-quality/spec.md`

## Summary

Tune Sonarr/Radarr quality profiles (P1), evaluate and onboard one or more paid private indexers in Prowlarr (P2), and tighten Deluge connection/queue/encryption settings on the Torrentbox Pi 5 (P3). All work lives on existing services — there is no new container, no new code path, and no repo-committed secret. The deliverables are: (a) updated Sonarr/Radarr configuration applied live through their UIs/APIs, (b) new Prowlarr indexer(s) added with app-sync propagated to Sonarr and Radarr, (c) a documented indexer evaluation artifact in `docs/`, and (d) an updated `docs/INFRASTRUCTURE.md` capturing the final Deluge tuning values and the names (not credentials) of the active paid indexers. Verification is manual and behavior-driven: trigger searches/grabs and inspect outcomes.

## Technical Context

**Language/Version**: N/A — this feature makes configuration changes to existing containerized services. A small verification helper may be written in Python 3.12 (already installed on the Mac) to query the Sonarr/Radarr/Prowlarr REST APIs during quickstart validation, but no new long-running code is produced.
**Primary Dependencies**: Existing Torrentbox stack — `linuxserver/sonarr`, `linuxserver/radarr`, `linuxserver/prowlarr`, `linuxserver/deluge`, `ghcr.io/flaresolverr/flaresolverr`. Existing PIA VPN container. No new images.
**Storage**: Container config volumes already mounted at `/home/john/docker/{sonarr,radarr,prowlarr,deluge}` on Torrentbox. No database changes. No repo-committed configuration files for indexer credentials.
**Testing**: Manual validation per `quickstart.md` (search + grab + re-search scenarios, health checks in Prowlarr, sustained-load check on the Pi). Optional Python verification script that hits each *arr REST API to assert profile presence, cutoff, and indexer health. No unit-test harness added.
**Target Platform**: Torrentbox Pi 5 (192.168.10.141) running Debian Trixie; services already operational. Configuration applied via each container's web UI or REST API, reached over the LAN from the Mac workstation.
**Project Type**: Infrastructure configuration + documentation feature. No application code is authored. Fits under the existing `infrastructure/` tree conceptually, but the authoritative state lives inside the containers' config volumes on the Pi, not in the repo.
**Performance Goals**: Per SC-001–SC-006 — 100% WEB-DL+ grabs, ≥50% seeder improvement, 90%+ search hit rate, zero size-cap violations, ≤2 upgrade re-grabs per item lifetime, Pi CPU <80% under sustained download.
**Constraints**: (a) No indexer credentials, API keys, or cookies committed to the repo (FR-017). (b) VPN routing for Deluge must not be broken (FR-018). (c) Deluge tuning must stay within the Pi 5's proven headroom. (d) FlareSolverr remains the CloudFlare path for protected indexers.
**Scale/Scope**: Single Torrentbox, ~2k current library items managed by Sonarr/Radarr, ~10–15 existing public indexers in Prowlarr, 1–2 paid private indexers added by this feature, roughly 2 quality profiles (TV, Movies) modified.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**I. Local-First** — Pass. All services remain on the LAN. Outbound queries to paid indexer sites fall under the constitution's explicit "torrent traffic" allowance. Credentials live inside Prowlarr on the Pi, not in any cloud store. No telemetry, no SaaS, no external auth.

**II. Simplicity & Pragmatism** — Pass. No new service, no new code, no new abstraction. Uses each existing container's native UI/API. Quality profiles and indexers are first-class features of Sonarr/Radarr/Prowlarr; using them as intended is simpler than any alternative.

**III. Containerized Everything** — Pass. Acts on the existing container stack; does not introduce bare-metal processes. Credentials stay inside container config volumes (gitignored in practice — they live only on the Pi).

**IV. Test-After (Not Test-First)** — Pass. Validation is manual + optional API-probe script, executed after changes are applied. No TDD pressure. The quickstart doubles as the behavioral test plan.

**V. Observability** — Pass. Prowlarr's per-indexer health view and Sonarr/Radarr history are the observability surfaces. No new `/health` endpoint needed because no new service is added. INFRASTRUCTURE.md update preserves the discoverability requirement.

**Result**: No violations. Complexity Tracking table below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/014-indexers-quality/
├── plan.md              # This file
├── research.md          # Phase 0: indexer comparison, TRaSH-guide alignment, Deluge-tuning refs
├── data-model.md        # Phase 1: Quality Profile + Indexer + Deluge Tuning entity shapes
├── quickstart.md        # Phase 1: Manual + API-driven validation procedure
├── contracts/
│   └── README.md        # Phase 1: Describes the external interfaces touched (Sonarr/Radarr/Prowlarr REST, Deluge RPC) — no schemas invented
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # /speckit.tasks output (not produced here)
```

### Source Code (repository root)

No new source code is produced by this feature. The only repo-level file changes are:

```text
docs/
├── INFRASTRUCTURE.md                 # UPDATED: Deluge Settings section (FR-015), Prowlarr Apps section lists new indexers by name (FR-017), Quality Profile summary subsection added
└── indexer-evaluation.md             # NEW: Evaluation of ≥3 candidate paid indexers with selection rationale (FR-006, FR-007)

# No code under src/, no containers in infrastructure/torrentbox/ (that directory is a future placeholder per CLAUDE.md).
# All runtime configuration changes live inside the Torrentbox Pi's container config volumes:
#   /home/john/docker/sonarr/config.xml, profiles/*   — not in this repo
#   /home/john/docker/radarr/config.xml, profiles/*   — not in this repo
#   /home/john/docker/prowlarr/config.xml, indexers/* — not in this repo
#   /home/john/docker/deluge/core.conf                — not in this repo
```

**Structure Decision**: **Documentation + external-service configuration feature.** The authoritative state lives inside the running containers on Torrentbox; the repo holds only the evaluation record and the human-readable tuning summary in INFRASTRUCTURE.md. No `infrastructure/torrentbox/` Compose file is introduced by this feature — CLAUDE.md already notes that as a future, separately-scoped effort. The spec directory holds research, design, and quickstart artifacts for this feature exclusively.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations to track.
