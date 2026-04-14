# Feature Specification: Indexers & Quality Optimization

**Feature Branch**: `014-indexers-quality`
**Created**: 2026-04-14
**Status**: Draft
**Input**: User description: "F5.1 Indexers and Quality Optimization - paid indexers in Prowlarr, tuned quality profiles in Sonarr/Radarr, optimized Deluge settings"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tune Sonarr/Radarr quality profiles (Priority: P1)

As a media consumer, I want Sonarr and Radarr to automatically prefer high-quality releases and reject low-quality ones so that every download defaults to a good watchable copy without manual intervention.

**Why this priority**: Quality profile tuning is the highest-leverage, lowest-cost change. It takes effect on every future download (hundreds per year), requires no external signup, and directly improves the end-user viewing experience on Plex. It is independent of the indexer and Deluge work.

**Independent Test**: Trigger a manual search on 3 TV episodes and 3 movies across the existing indexer set, confirm the selected grabs exclude CAM/TS and prefer Bluray/WEB-DL over HDTV, and that sizes fall within the configured caps. Verified without any new indexer or Deluge change.

**Acceptance Scenarios**:

1. **Given** a TV episode is requested, **When** only a CAM or TS release is available, **Then** Sonarr rejects it and keeps searching rather than grabbing it.
2. **Given** an HDTV 720p copy of an episode has already been downloaded, **When** a Bluray 1080p copy later appears, **Then** Sonarr automatically upgrades up to the configured cutoff and replaces the earlier file.
3. **Given** a movie has multiple candidate releases, **When** Radarr evaluates them, **Then** it selects the highest-priority release that also falls below the configured maximum size limit.
4. **Given** a release exceeds the configured maximum size, **When** Radarr evaluates it, **Then** it is rejected regardless of quality tier.

---

### User Story 2 - Onboard paid indexers in Prowlarr (Priority: P2)

As a media consumer, I want at least one paid private indexer evaluated, signed up for, and wired into Prowlarr so that Sonarr and Radarr can search a larger, better-seeded catalog automatically.

**Why this priority**: Private indexers substantially expand content availability and seeder counts, but they carry recurring cost, signup effort, and in some cases invite/interview gating, so they come after the free quality-profile win. Without quality profiles (P1) in place first, better indexers would just surface more random-quality releases.

**Independent Test**: After selecting and adding the indexer, run a Prowlarr test on it, confirm Sonarr and Radarr can see it in their indexer list via the Prowlarr sync, and run a search in each for a recent TV episode and a recent movie, confirming results include entries from the new indexer.

**Acceptance Scenarios**:

1. **Given** at least three candidate paid indexers, **When** their cost, content catalog, seeder health, and signup gating are compared, **Then** a documented selection decision exists with rationale captured in project docs.
2. **Given** a selected indexer with an active account, **When** the indexer is added to Prowlarr with credentials/API key, **Then** Prowlarr's built-in test passes for that indexer.
3. **Given** Prowlarr has a new indexer configured, **When** app sync runs, **Then** the same indexer appears in both Sonarr and Radarr without manual re-entry, and searches from those apps return results from it.
4. **Given** a CloudFlare-protected indexer is among those configured, **When** Prowlarr queries it, **Then** FlareSolverr handles the challenge transparently and results are returned.
5. **Given** the indexer is active for at least 7 days, **When** grab history is reviewed, **Then** availability (hit rate on searches) and seeder counts have measurably improved compared to the public-only baseline.

---

### User Story 3 - Optimize Deluge connection and queue settings (Priority: P3)

As a media consumer, I want Deluge on the Torrentbox Pi 5 tuned for its hardware and network so that downloads complete faster, seeding is bounded, and the Pi is not saturated.

**Why this priority**: Deluge tuning yields incremental speed and stability gains but produces no new content on its own. It is the last piece because the upstream decisions (which releases to grab, from where) matter more than how fast a bad grab downloads.

**Independent Test**: Apply the tuned settings, download a known-healthy torrent, and confirm: (a) the Pi's CPU and memory stay within healthy bounds during download, (b) active-download and seeding-ratio limits are honored when multiple torrents queue, (c) encryption is forced on the connection, (d) the tuned values are captured in INFRASTRUCTURE.md.

**Acceptance Scenarios**:

1. **Given** more torrents are queued than the configured active-download limit, **When** downloads start, **Then** only the configured number run concurrently and the rest wait in queue.
2. **Given** a torrent has reached the configured seeding ratio, **When** that ratio is met, **Then** Deluge stops seeding it per policy.
3. **Given** Deluge is configured for forced encryption, **When** a connection is attempted with a peer that does not support encryption, **Then** the connection is refused.
4. **Given** the tuning is complete, **When** a reader opens INFRASTRUCTURE.md, **Then** they find the current Deluge connection and queue settings documented with values.

---

### Edge Cases

- **Indexer outage**: If a paid indexer becomes unreachable (site down, account suspended, rate-limited), Sonarr/Radarr searches must still return results from remaining indexers rather than failing outright.
- **Quality profile starvation**: If a profile is so strict that no release ever qualifies (e.g., a rare older show with only HDTV copies), the release waits indefinitely. The profile design must balance strictness against availability for catalog depth.
- **Upgrade churn**: An over-eager upgrade cutoff can trigger repeated re-downloads as higher-quality versions appear; the cutoff must be set so upgrades terminate at a reasonable tier.
- **CloudFlare challenge drift**: Indexer site changes can break FlareSolverr; the system must surface a clear error in Prowlarr rather than silently returning empty results.
- **Paid indexer invite/ratio lapse**: Some private trackers require minimum ratio or activity; if the account is disabled, the indexer returns auth failures. Failures must be visible in Prowlarr's indexer health view.
- **Pi resource pressure**: If Deluge connection limits are set too high for the Pi 5, torrent performance and other services (VPN, *arr apps) degrade. Tuning must stay within the device's proven headroom.
- **Size-limit conflict with upgrade**: A higher quality tier may exceed the configured size cap. The system must not upgrade to a release that violates size policy even if its quality tier is preferred.

## Requirements *(mandatory)*

### Functional Requirements

#### Quality Profiles (Sonarr & Radarr)

- **FR-001**: Quality profiles MUST reject CAM, TS, TC, SCR, and other low-grade theatrical/pre-release quality tags outright. Standard-definition tiers (DVDRip, SDTV, 480p) are also excluded to enforce the 1080p-minimum baseline.
- **FR-002**: Quality profiles MUST rank allowed qualities in the priority order: Bluray Encode (1080p) > WEB-DL (1080p) > WEBRip (1080p), with lower tiers only accepted when no higher tier is available. Bluray Remux and HDTV are excluded from the default profile — Remux bitrates exceed the storage-conscious size caps mandated by FR-003, and HDTV does not meet the 1080p baseline.
- **FR-003**: Quality profiles MUST enforce a per-release maximum size cap, with separate caps appropriate to TV episodes and to movies.
- **FR-004**: Quality profiles MUST define an upgrade cutoff such that once a file at or above the cutoff tier is present, no further upgrades occur for that item.
- **FR-005**: Quality profiles MUST be applied as the default profile for new series and movies added to Sonarr and Radarr respectively.

#### Paid Indexers (Prowlarr)

- **FR-006**: The evaluation MUST document at least three candidate paid indexers, comparing cost, content catalog (TV/Movies/other), seeder health, and signup gating (open vs. invite-only vs. interview).
- **FR-007**: The final indexer selection decision MUST be recorded in project documentation with rationale.
- **FR-008**: Prowlarr MUST be configured with valid credentials or API keys for each selected paid indexer, and each indexer's built-in test MUST pass.
- **FR-009**: Prowlarr-to-Sonarr and Prowlarr-to-Radarr app sync MUST propagate the new indexers automatically; no indexer configuration is entered directly in Sonarr or Radarr.
- **FR-010**: CloudFlare-protected indexers MUST continue to be resolved via the existing FlareSolverr deployment.
- **FR-011**: Prowlarr MUST surface per-indexer health so outages, auth failures, or rate-limit issues are visible without inspecting container logs.

#### Deluge Optimization

- **FR-012**: Deluge MUST enforce a global maximum connection count and per-torrent connection count appropriate to the Torrentbox Pi 5's CPU, RAM, and VPN throughput.
- **FR-013**: Deluge MUST have encryption set to forced (both incoming and outgoing) for peer connections.
- **FR-014**: Deluge MUST cap the number of concurrently active downloads and enforce a seeding ratio (or seeding time) policy, after which torrents stop seeding.
- **FR-015**: The final Deluge tuning values MUST be recorded in INFRASTRUCTURE.md alongside the Torrentbox section.

#### Cross-cutting

- **FR-016**: All changes MUST be made on the existing Torrentbox and HOLYGRAIL deployments without introducing new host machines or Docker hosts.
- **FR-017**: Credentials, API keys, and cookies for paid indexers MUST NOT be committed to the repository; they are configured in Prowlarr and referenced by docs only by name.
- **FR-018**: The system MUST continue to route Deluge traffic through the existing VPN container; quality or indexer changes must not bypass the VPN.

### Key Entities *(data-adjacent, not DB-backed)*

- **Quality Profile**: A named set of allowed quality tiers, their priority ranking, a maximum size cap, and an upgrade cutoff. One profile applies per media type (TV, Movies). Lives in Sonarr/Radarr configuration.
- **Indexer**: A searchable release source with name, type (public/private), credentials/API key, CloudFlare status, and health state. Managed in Prowlarr and synced to Sonarr/Radarr.
- **Indexer Evaluation Record**: A documentation artifact capturing the candidate indexers considered, their attributes (cost, catalog, gating, seeder health), and the selection decision with rationale.
- **Deluge Tuning Profile**: The set of connection-limit, encryption, active-download, and seeding-ratio values applied to the Deluge daemon on Torrentbox, captured in INFRASTRUCTURE.md.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After quality-profile tuning, 100% of automatically grabbed releases (TV and movies) are at WEB-DL tier or higher for at least 4 consecutive weeks of normal usage; zero CAM/TS/SCR grabs occur.
- **SC-002**: Average seeder count on grabbed torrents increases by at least 50% compared to a pre-change baseline of the preceding 30 days of history.
- **SC-003**: Search hit rate — the proportion of Sonarr/Radarr searches that return at least one acceptable release under the new quality profile — reaches 90% or higher for mainstream catalog items within 30 days of paid-indexer activation.
- **SC-004**: Every grabbed release is within its configured size cap; zero releases exceed the cap once the feature is live.
- **SC-005**: Upgrade churn is bounded: no item in the library is replaced more than twice by the upgrade system over its lifetime.
- **SC-006**: Torrentbox Pi 5 sustains full-saturation downloads under the new Deluge limits without CPU load exceeding 80% or memory pressure triggering swap.
- **SC-007**: All paid indexers report healthy in Prowlarr for at least 95% of a rolling 30-day window (excluding planned maintenance).
- **SC-008**: INFRASTRUCTURE.md, read without context, is sufficient for a new operator to reproduce the current Deluge tuning and list the active paid indexers (by name, not credentials).

## Assumptions

- The existing Prowlarr, Sonarr, Radarr, Deluge, and FlareSolverr deployments on the Torrentbox Pi 5 are healthy and remain the hosts for this feature; no migration to HOLYGRAIL is in scope.
- The user is willing to pay recurring fees for at least one private tracker; a reasonable annual budget envelope of roughly US$50–US$150 is assumed unless otherwise constrained. Exact spend falls out of the evaluation in US-2.
- Target content is mainstream English-language TV and movies for Plex; niche categories (anime, foreign, music, ebooks) are not optimized for in this phase but are not excluded if a chosen indexer happens to cover them.
- Storage headroom on the NAS is sufficient to absorb upgrade churn (occasional re-grabs at higher quality); the NAS capacity strategy is handled separately in Phase 7.
- VPN egress bandwidth on the Torrentbox remains the effective bottleneck before Pi CPU; Deluge tuning assumes this and favors conservative connection limits over aggressive parallelism.
- The existing Prowlarr → Sonarr/Radarr app sync configuration is functional; this feature extends it but does not redesign it.
- Credentials/API keys will be entered directly into Prowlarr's UI (or via its settings file outside the repo); the repo will only reference indexers by name.
- "Seeders improved" baselines (SC-002, SC-003) are computed from Sonarr/Radarr grab history, which is assumed to be retained long enough to support the 30-day comparison.
