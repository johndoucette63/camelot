# Phase 1 Data Model: Indexers & Quality Optimization

**Feature**: 014-indexers-quality
**Date**: 2026-04-14

This feature does not add database tables. The entities below describe the **configuration shapes** that live inside Sonarr, Radarr, Prowlarr, and Deluge container config volumes on the Torrentbox Pi 5, plus one documentation artifact in the repo. They are captured here so the quickstart and any future verification script know what to look for.

---

## E1. Quality Profile

**Lives in**: Sonarr (`/home/john/docker/sonarr/config/...`) and Radarr (`/home/john/docker/radarr/config/...`) on Torrentbox.
**Accessible via**: `GET /api/v3/qualityprofile` on each app's REST API.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Profile identifier. Standardize on `HD Bluray + WEB` (TRaSH convention). |
| `upgradeAllowed` | bool | `true` — upgrades are enabled. |
| `cutoff` | quality id | Points to `Bluray-1080p` quality. |
| `items[]` | list of quality groups, ordered | Allowed qualities + their relative priority, lowest-to-highest. |
| `minFormatScore` | int | `0` for the default profile. |
| `cutoffFormatScore` | int | `10000` — intentionally unreachable, so upgrades never stop prematurely. |
| `formatItems[]` | list of Custom Format references + scores | TRaSH CFs; negative scores reject junk (BR-DISK, EVO, x265 HD, AV1). |
| `language` | language id | `English`. |

### Validation (from Requirements)

- `items[]` MUST exclude CAM/TS/TC/SCR tiers (FR-001).
- `items[]` MUST order qualities: Bluray Remux > Bluray Encode > WEB-DL > WEBRip > HDTV (FR-002).
- `cutoff` + `cutoffFormatScore = 10000` together define the upgrade stop condition (FR-004).
- The profile MUST be set as the default on new series / movies in the respective app (FR-005).
- Size caps are enforced via the `Quality Definitions` (per-media-type, app-level) — not on the profile itself — but logically bound to this entity (FR-003).

### State transitions

None. A profile is a static configuration document that is versioned only manually when TRaSH updates its recommendations.

---

## E2. Quality Definition (size bands)

**Lives in**: Sonarr and Radarr (app-level, not profile-level).
**Accessible via**: `GET /api/v3/qualitydefinition` on each app's REST API.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `quality.id` | int | Points to a quality tier (e.g., `WEBDL-1080p`, `Bluray-1080p`). |
| `quality.name` | string | Human-readable tier name. |
| `minSize` | float MB/min | Lower size bound. |
| `preferredSize` | float MB/min | Hint for preferred tier. |
| `maxSize` | float MB/min | Upper size bound — enforces the feature's per-release cap (FR-003). |

### Decisions for this feature

Storage-conscious caps: hard ceiling ≈ 10 GB per file, preferred 3–6 GB band. Numbers chosen so typical runtimes land mid-band.

| Media | Tier | `minSize` | `preferredSize` | `maxSize` | Implied size at typical runtime |
|-------|------|-----------|-----------------|-----------|---------------------------------|
| TV (Sonarr) | WEBDL-1080p | 15 | 45 | 80 | 45-min ep: ~2.0 GB preferred / ~3.6 GB cap |
| TV (Sonarr) | Bluray-1080p | 50 | 55 | 80 | 60-min ep: ~3.3 GB preferred / ~4.8 GB cap |
| Movies (Radarr) | WEBDL-1080p | 15 | 45 | 55 | 120-min movie: ~5.4 GB preferred / ~6.6 GB cap |
| Movies (Radarr) | Bluray-1080p | 50 | 50 | 55 | 180-min movie (worst case): ~9.0 GB preferred / ~9.9 GB cap |

All values in MB/min. These satisfy SC-004 (zero grabs exceed the cap) and the operator's storage preference: ≤ 10 GB hard, 3–6 GB preferred. Effect: WEB-DL at 40–55 MB/min is the typical grab; high-bitrate Bluray encodes (80+ MB/min) are rejected in favor of WEB-DL. Accepted trade-off.

---

## E3. Indexer (Prowlarr-managed)

**Lives in**: Prowlarr (`/home/john/docker/prowlarr/config/...`).
**Accessible via**: `GET /api/v1/indexer` on Prowlarr's REST API.
**Propagates to**: Sonarr and Radarr via app-sync; in those apps, read-only (Prowlarr-badged).

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name (e.g., `IPTorrents`). |
| `definitionName` | string | Cardigann definition identifier. |
| `implementation` | string | `Cardigann` / `Torznab` / native type. |
| `protocol` | enum | `torrent`. |
| `baseUrl` | string | Indexer site URL. |
| `fields[]` | list of key-value | Credentials (API key, cookie, username/password). **Never in repo.** |
| `tags[]` | list of tag ids | Includes `tv`, `movies`, and `flaresolverr` if CloudFlare-gated. |
| `enable` | bool | `true` if active. |
| `priority` | int (1–50) | Lower = higher priority. |
| `redirect` | bool | `false` for most; `true` for some trackers. |
| `supportsSearch` / `supportsRss` | bool | Capability flags. |
| `categories[]` | list of category ids | Must include TV (5000–5999) to sync to Sonarr, Movies (2000–2999) to sync to Radarr. |

### Health

Prowlarr exposes a per-indexer health view with three states:

| State | Meaning | Action |
|-------|---------|--------|
| **OK** | Last test + last query succeeded. | None. |
| **Warning** | Cookies expiring, captcha pending, rate-limited, or FlareSolverr needed but not applied. | Investigate; searches still run. |
| **Error** | Auth failed, tracker down, definition broken. | Searches disabled for this indexer until fixed. |

### Validation (from Requirements)

- Each indexer MUST pass Prowlarr's built-in Test (FR-008).
- Each indexer MUST sync to both Sonarr and Radarr when tags + categories align (FR-009).
- CloudFlare-gated indexers MUST have the `flaresolverr` tag (FR-010).
- Credentials (`fields[]` with key-like names) MUST NOT be committed to the repo (FR-017).

---

## E4. Indexer Proxy (FlareSolverr)

**Lives in**: Prowlarr, Settings → Indexers → Indexer Proxies.
**Accessible via**: `GET /api/v1/indexerproxy` on Prowlarr's REST API.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | `FlareSolverr`. |
| `implementation` | string | `FlareSolverr`. |
| `host` | string | `http://flaresolverr:8191/` (container-internal DNS). |
| `tags[]` | list of tag ids | Includes `flaresolverr` — only indexers with this tag route through the proxy. |

**Expected state**: Exactly one FlareSolverr proxy exists, with the `flaresolverr` tag. (Already present per INFRASTRUCTURE.md — this feature verifies, does not create.)

---

## E5. App (Sonarr/Radarr as seen from Prowlarr)

**Lives in**: Prowlarr, Settings → Apps.
**Accessible via**: `GET /api/v1/applications` on Prowlarr.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | `Sonarr` / `Radarr`. |
| `implementation` | string | `Sonarr` / `Radarr`. |
| `syncLevel` | enum | MUST be `fullSync`. |
| `prowlarrUrl` | string | Prowlarr's own URL as seen by Sonarr/Radarr. |
| `baseUrl` | string | Sonarr/Radarr URL, e.g., `http://sonarr:8989`. |
| `apiKey` | string | Sonarr/Radarr API key (already present in INFRASTRUCTURE.md per existing setup). |
| `syncCategories[]` | list of category ids | TV (5000–5999) for Sonarr; Movies (2000–2999) for Radarr. |
| `tags[]` | list of tag ids | MUST match the indexer-side tags (`tv` for Sonarr, `movies` for Radarr). |

---

## E6. Deluge Tuning Profile

**Lives in**: Deluge daemon config on Torrentbox (`/home/john/docker/deluge/core.conf`).
**Accessible via**: Deluge Web UI → Preferences, or Deluge RPC (port 58846).

### Fields (matches `core.conf` keys)

| Key | Type | Target value (from research R3) |
|-----|------|----------------------------------|
| `max_connections_global` | int | 200 |
| `max_connections_per_torrent` | int | 50 |
| `max_active_downloading` | int | 3 |
| `max_active_seeding` | int | 5 |
| `max_active_limit` | int | 8 |
| `max_upload_slots_global` | int | 40 |
| `max_upload_slots_per_torrent` | int | 4 |
| `enc_in_policy` | int | 2 (Forced) |
| `enc_out_policy` | int | 2 (Forced) |
| `enc_allow_legacy` | bool | false |
| `dht` | bool | false |
| `lsd` | bool | false |
| `utpex` | bool | false |
| `upnp` | bool | false |
| `natpmp` | bool | false |
| `listen_ports` | [int, int] | `[P, P]` where `P` is the PIA-forwarded port |
| `listen_interface` | string | VPN tun/wg IP (e.g., `10.x.x.x`) |
| `outgoing_ports` | [int, int] | `[0, 0]` |
| `stop_seed_at_ratio` | bool | true |
| `stop_seed_ratio` | float | 1.5 |
| `remove_seed_at_ratio` | bool | false (keep torrent registered for a manual prune) |

### Validation (from Requirements)

- Encryption MUST be forced both directions (FR-013).
- Active-download cap and seeding-ratio policy MUST be enforced (FR-014).
- Values MUST be recorded in `docs/INFRASTRUCTURE.md` (FR-015).

---

## E7. Indexer Evaluation Record (repo artifact)

**Lives in**: `docs/indexer-evaluation.md` (new file produced by this feature).

### Required content

- **Candidates considered** (≥ 3): rows for each with name, approximate cost, content focus, signup gating, Prowlarr native support, CloudFlare status.
- **Selection decision**: which indexer(s) chosen.
- **Rationale**: one paragraph per chosen indexer explaining the trade-off.
- **What was rejected and why** for each non-chosen candidate.
- **NO credentials, API keys, cookies, or invite codes.** Names only.

### Validation

- Satisfies FR-006 (≥ 3 candidates documented) and FR-007 (decision recorded with rationale).

---

## Relationships

```text
QualityProfile (1) ——applies to——> (n) Series / Movie
QualityDefinition (n) ——references——> (n) quality tiers (app-level, shared across profiles)

Indexer (n) ——tagged with——> Tag (n)          ; matching drives sync + proxy selection
Tag (n) ——matched against——> App.tags
Tag (n) ——matched against——> IndexerProxy.tags

Indexer ——synced via——> App (Sonarr/Radarr)    ; only if Tags + Categories intersect
Indexer ——routed via——> IndexerProxy           ; only if Tag "flaresolverr" applied

DelugeTuningProfile (1) ——applies to——> Deluge daemon (1)
IndexerEvaluationRecord (1) ——documents——> Indexer (n) candidates considered
```

No state machines — these are all static configuration documents that change by direct edit.
