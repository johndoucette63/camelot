# Phase 0 Research: Indexers & Quality Optimization

**Feature**: 014-indexers-quality
**Date**: 2026-04-14
**Purpose**: Resolve all open decisions before design. Each entry captures what was chosen, why, and what was rejected.

---

## R1. Which paid/private indexer(s) to pursue first

**Decision**: Onboard **IPTorrents (IPT)** as the day-1 paid indexer. Attempt **TorrentLeech (TL)** opportunistically if a donation/signup window opens during this feature's implementation window. Leave BTN / PTP / HDBits as aspirational long-term goals, not scope here.

**Rationale**:

- IPT is open via one-time donation (no interview, no invite), Prowlarr has native Cardigann support, and its general-content swarm covers TV + Movies + sports broadly — the highest ROI for a Plex-centric catalog.
- TL is similar quality but gated behind periodic donation windows. Treat it as bonus, not blocker.
- BTN/PTP/HDBits are effectively sealed behind invite chains and interviews. Their quality is unmatched but acquiring access is a multi-month effort, well outside the scope of this feature.
- FileList is a reasonable secondary but is CloudFlare-gated and Romanian-first; adds complexity without proportional catalog gain for English-language use.

**Alternatives considered**:

- **IPT + TL day 1** — TL signup isn't reliably available; can't plan around it.
- **Interview path to RED/Orpheus → BTN/PTP** — too long a lead time, doesn't fit this feature window, and audio-first trackers (RED) don't help Plex TV/Movies directly.
- **Stay on public indexers only** — fails the feature's core goal (improved seeders + availability).

---

## R2. Quality profile design (Sonarr + Radarr)

**Decision**: Adopt the **TRaSH Guides `HD Bluray + WEB` profile** as the default for both Sonarr (TV) and Radarr (Movies). Apply the accompanying **Custom Formats** (CFs) with TRaSH's recommended scores. Set **Upgrade Until Custom Format Score = 10000** (intentionally unreachable) and **quality cutoff = Bluray-1080p**. Mark junk tags (BR-DISK, EVO, x265 for HD, AV1) with `-10000` to reject outright.

**Rationale**:

- TRaSH's profiles are the de facto community standard for 2025 and encode the exact rejection/priority logic the spec requires (FR-001, FR-002).
- CFs + a high unreachable upgrade score let the system always accept a better release when one appears, without prematurely locking in at the cutoff tier — directly supports FR-004 and the "upgrade HDTV → Bluray" acceptance scenario.
- The profile natively bands allowed qualities as Bluray-1080p > WEBDL-1080p > WEBRip-1080p, matching FR-002.

**Size-cap decision** (FR-003): The operator wants a **storage-conscious** profile — hard cap < 10 GB per file, preferred band 3–6 GB — balancing quality against NAS capacity. TRaSH's defaults lean generous (12–15 GB movies routine) and are tightened here.

- **Movies (Radarr)**: WEBDL-1080p `min=15, preferred=45, max=55` MB/min; Bluray-1080p `min=50, preferred=50, max=55` MB/min.
  - 100-min movie: ≈ 4.5 GB preferred / 5.5 GB cap (centered in the 3–6 GB band).
  - 120-min movie: ≈ 5.4 GB preferred / 6.6 GB cap.
  - 180-min movie (rare epic): ≈ 9 GB preferred / 9.9 GB cap — just under the 10 GB hard line.
- **TV (Sonarr)**: WEBDL-1080p `min=15, preferred=45, max=80` MB/min; Bluray-1080p `min=50, preferred=55, max=80` MB/min.
  - 45-min episode: ≈ 2 GB preferred / 3.6 GB cap.
  - 60-min episode: ≈ 2.7 GB preferred / 4.8 GB cap.
  - 90-min miniseries episode (rare): ≈ 4 GB preferred / 7.2 GB cap.
- These ceilings effectively **prefer WEB-DL over Bluray** for most titles (high-bitrate Bluray encodes at 80+ MB/min are rejected), which aligns with the storage-balance goal: WEB-DL at 40–55 MB/min looks excellent on Plex.
- 2160p/4K is **excluded** from the default profile — its storage cost is incompatible with the 10 GB ceiling.
- Trade-off accepted: occasional high-bitrate Bluray Remux releases (80+ MB/min) will be rejected in favor of WEB-DL. The operator prioritizes library capacity over the last increment of visual quality.

**Tooling**: Profile sync via **Recyclarr** is the best practice but is **out of scope for this feature**. Manual TRaSH-aligned setup is acceptable; Recyclarr adoption can be a follow-up.

**Alternatives considered**:

- **Hand-rolled profile from scratch** — rejected. Reinvents TRaSH, misses CF nuance, higher maintenance.
- **WEB-1080p only (no Bluray tier)** — rejected. Loses the clear upgrade path from HDTV/WEB-DL to Bluray.
- **Include 2160p/Remux tiers** — rejected for this phase. Storage cost not justified until Phase 7 NAS evolution.

---

## R3. Deluge tuning values

**Decision**: Apply the following values on the Torrentbox Pi 5 (8 GB RAM, Debian Trixie, behind PIA VPN container):

| Setting | Value |
|---------|-------|
| `max_connections_global` | 200 |
| `max_connections_per_torrent` | 50 |
| `max_active_downloading` | 3 |
| `max_active_seeding` | 5 |
| `max_active_limit` | 8 |
| `max_upload_slots_global` | 40 |
| `max_upload_slots_per_torrent` | 4 |
| Encryption (outgoing) | forced |
| Encryption (incoming) | forced |
| `allow_legacy_in` | false |
| DHT / LSD / PEX | off |
| UPnP / NAT-PMP | off |
| `listen_ports` | pinned to PIA-forwarded port (single port) |
| `listen_interface` | bound to VPN `tun`/`wg` interface IP (kill-switch hygiene) |
| `outgoing_ports` | 0, 0 (unconstrained) |
| Seed-ratio stop | 1.5 ratio, or 7 days — whichever first |

**Rationale**:

- 200 global / 50 per-torrent is within the Pi 5's headroom and respects PIA's NAT/port-forward as the effective bottleneck rather than Pi CPU.
- Forced encryption both ways (FR-013) prevents ISP RST injection and mirrors private-tracker expectations.
- DHT/LSD/PEX off is mandatory for private trackers — leaks can trigger bans.
- Binding `listen_interface` to the VPN interface is the critical kill-switch detail: if the tunnel drops, Deluge cannot fall back to `eth0`. This protects FR-018 (VPN routing must not be bypassed).
- Seeding ratio 1.5 / 7 days balances peer etiquette with the Pi's finite disk and the feature's SC-005 (bounded upgrade churn + predictable disk reclaim).

**Alternatives considered**:

- **Higher global connections (400+)** — rejected. No measurable benefit given PIA throughput; risks Pi contention with *arr apps.
- **Encryption "enabled" instead of "forced"** — rejected. Doesn't meet FR-013 literal requirement.
- **Leave DHT on for public indexers** — rejected. Mixed DHT-on on a client that talks to private trackers risks bans; safer to gate per-torrent-private flag and keep globals off.

---

## R4. Prowlarr app-sync configuration

**Decision**: Configure Prowlarr → Sonarr/Radarr app sync with **Sync Level = Full Sync**, adopt a minimal tag taxonomy (`tv`, `movies`, `flaresolverr`), and apply tags consistently across indexers, apps, and the FlareSolverr proxy. Click **Test All Indexers** + **Sync App Indexers** manually after every indexer add instead of waiting on the 12-hour cycle. Verify sync success by presence of the Prowlarr badge on the Sonarr/Radarr Indexers list (not by inspecting Prowlarr alone).

**Rationale**:

- Tag-matching is the #1 cause of "added indexer doesn't appear in Sonarr/Radarr." The explicit three-tag taxonomy eliminates that failure mode.
- Full Sync (vs Add Only / Disabled) is required to propagate updates — matches the "sync verified" acceptance criterion in the feature spec.
- FlareSolverr proxy routes only tagged indexers. Without the `flaresolverr` tag on a CloudFlare-gated indexer, Prowlarr queries directly and returns empty results silently — this would violate the feature's Edge Case ("CloudFlare challenge drift — surface clear error").

**Alternatives considered**:

- **No tags (global push)** — rejected. Works initially but breaks when a TV-only indexer leaks into Radarr or a category-gated query fails.
- **Per-indexer proxy selection** — rejected. More configuration surface; tags are the idiomatic path.

---

## R5. Indexer health observability

**Decision**: Use **Prowlarr's built-in System → Health + per-indexer History views** as the single source of truth for indexer status (FR-011). No new dashboard, no InfluxDB metric, no custom exporter for this feature.

**Rationale**:

- Prowlarr's native surfaces already distinguish OK / Warning / Error cleanly and link each failure to the cause (auth failed, CF challenge, rate-limited, tracker down).
- Adding a Grafana panel for indexer health is nice-to-have but is Phase 8 territory, not this feature's scope.
- Constitution V (Observability) is satisfied because indexer health is already observable via the container's UI — no silent failure path is introduced.

**Alternatives considered**:

- **Scrape Prowlarr's API into InfluxDB for Grafana** — deferred. Reasonable, but scope creep. Log as a follow-up for Phase 8.
- **Email/Telegram alerts on indexer Error state** — out of scope; aligns better with Phase 4.5's existing notification sinks.

---

## R6. Verification approach

**Decision**: Validate via the **quickstart.md behavioral procedure** — manual searches, grabs, health inspection, and a sustained-load run on the Pi. Optionally, run a small Python helper (`scripts/verify-014.py`, not committed unless genuinely useful) that hits each *arr REST API and asserts: profile name present, upgrade cutoff set to Bluray-1080p, each target indexer present + healthy, Prowlarr app-sync sees both Sonarr and Radarr. No pytest harness, no CI.

**Rationale**:

- Constitution IV (Test-After) says manual/behavioral validation after implementation is acceptable; no TDD pressure.
- The feature's success criteria are empirically verifiable (grab a real release, count seeders) — unit testing would add friction without signal.

**Alternatives considered**:

- **Write a pytest suite** — rejected. Over-engineered for a configuration feature.
- **Nothing automated at all** — rejected. The optional API-probe script prevents silent config drift and is cheap.

---

## R7. Operational risks + mitigations

| Risk | Mitigation |
|------|------------|
| `:latest` image tag pulls a breaking *arr release mid-feature | Pin image tags in any Compose edits; use current known-good: Sonarr ≥ 4.0.10, Radarr ≥ 5.x current, Prowlarr latest stable, FlareSolverr 3.3.x, Deluge linuxserver latest. |
| FlareSolverr memory creep on Pi 5 | Acceptable (~500 MB resident; Pi has 8 GB). Pin image tag; don't let it restart-loop. |
| DHT leaks ban the PIA IP on private tracker | Globals off in Deluge core; rely on per-torrent `private` flag semantics as secondary defence. |
| Paid indexer account lapses unnoticed | Prowlarr Error state surfaces this; no extra alerting added here. Re-check weekly by habit. |
| Jackett legacy definitions drift | This feature does not touch Jackett; if any Jackett indexers remain, migrate them to Prowlarr as part of this work. |

---

## Resolved NEEDS CLARIFICATION

None outstanding. The spec's Assumptions section captured the budget envelope, content focus, and VPN-bandwidth-as-bottleneck stance up front, so no open questions reached this research phase.
