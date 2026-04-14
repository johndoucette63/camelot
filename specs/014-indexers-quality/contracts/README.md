# Contracts: Indexers & Quality Optimization

**Feature**: 014-indexers-quality
**Date**: 2026-04-14

This feature does **not define any new public contract**. It consumes existing, stable REST APIs exposed by Sonarr, Radarr, and Prowlarr (and, if needed, Deluge's JSON-RPC endpoint) to read and write configuration. Those APIs are defined and versioned by the upstream projects — this document describes which endpoints are touched, at what version, and for which requirement. No schemas are invented here.

---

## External APIs consumed (read + write)

### Sonarr v3 REST API (running Sonarr v4.0.10+)

Base URL on LAN: `http://192.168.10.141:8989/api/v3`
Auth: `X-Api-Key` header, key already present in `docs/INFRASTRUCTURE.md`.

| Endpoint | Used for | Mapped requirement |
|----------|----------|--------------------|
| `GET /qualityprofile` | Verify profile `HD Bluray + WEB` exists; inspect cutoff and format scores | FR-002, FR-004 |
| `PUT /qualityprofile/{id}` | Update profile if drift detected | FR-002, FR-004, FR-005 |
| `GET /qualitydefinition` | Read size caps per tier | FR-003 |
| `PUT /qualitydefinition/update` | Set TV size caps (bulk) | FR-003 |
| `GET /customformat` | Verify TRaSH CFs present | FR-001, FR-002 |
| `GET /history` | Post-hoc validation of grab quality for SC-001 | SC-001, SC-002 |
| `GET /indexer` | Confirm Prowlarr-badged indexers visible | FR-009 |
| `GET /health` | Overall app-level health | Observability |

### Radarr v3 REST API (running Radarr v5.x)

Base URL on LAN: `http://192.168.10.141:7878/api/v3`
Auth: `X-Api-Key` header.

Same shape as Sonarr; mirror the endpoints above with Movies-specific caps.

### Prowlarr v1 REST API

Base URL on LAN: `http://192.168.10.141:9696/api/v1`
Auth: `X-Api-Key` header.

| Endpoint | Used for | Mapped requirement |
|----------|----------|--------------------|
| `GET /indexer` | Enumerate configured indexers, confirm new ones present | FR-008, FR-011 |
| `POST /indexer/test` | Run the built-in test against each newly added indexer | FR-008 |
| `GET /applications` | Verify Sonarr + Radarr apps configured with `syncLevel=fullSync` | FR-009 |
| `POST /applications/test` | Verify Prowlarr can reach Sonarr/Radarr | FR-009 |
| `GET /indexerproxy` | Verify FlareSolverr proxy exists and is tagged | FR-010 |
| `GET /health` | Per-indexer health surface | FR-011 |
| `POST /command` (`name=ApplicationIndexerSync`) | Force app-sync after adding a new indexer | FR-009 |

### Deluge JSON-RPC (optional touch)

Host: `torrentbox:58846` (RPC) or Web UI at `http://192.168.10.141:8112`.

The spec does not require programmatic Deluge configuration — the Web UI's Preferences dialog is the primary edit surface. Any scripting we do is read-only to confirm `core.conf` values match the target (E6 in `data-model.md`).

---

## Contracts produced by this feature

**None.** No new HTTP endpoints, no new CLI surface, no new files that other tools import from. The repo gains two documentation files (`docs/indexer-evaluation.md` new, `docs/INFRASTRUCTURE.md` updated) — neither is a machine-consumed contract.

---

## Versioning stance

Upstream API versions (Sonarr v3 API, Prowlarr v1 API) are stable and follow semver under the upstream projects' control. This feature pins nothing; if upstream bumps to a new major API, a future feature can address the migration. Per research R7, image tags for the underlying containers should be pinned away from `:latest` to avoid surprise breakage — but that tagging discipline is not itself a contract of this feature.

---

## Security considerations

- API keys for Sonarr/Radarr/Prowlarr are already documented inside `docs/INFRASTRUCTURE.md` for operator reference. They grant full control of the torrent stack on the LAN. Do not expose these APIs outside the LAN (no Traefik route to the public internet for these).
- Paid-indexer credentials and cookies live **only** in Prowlarr's config volume on the Pi. They are never written into the repo, the evaluation doc, or any spec artifact (FR-017).
