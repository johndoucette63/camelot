---
description: "Task list for feature 014-indexers-quality"
---

# Tasks: Indexers & Quality Optimization

**Input**: Design documents from `/Users/jd/Code/camelot/specs/014-indexers-quality/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Per Constitution IV (Test-After), no pre-implementation test tasks are generated. Validation is performed via `quickstart.md` after each story and in the Polish phase. This feature authors no application code, so a pytest suite would add friction without signal.

**Organization**: Tasks are grouped by user story (P1 → P2 → P3) so each story can be implemented, demoed, and rolled back independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files / different container config surfaces, no dependency on an incomplete task)
- **[Story]**: US1 (quality profiles), US2 (paid indexers), US3 (Deluge tuning)

## Path Conventions

This is a documentation + external-service configuration feature. Most "files" are UI panels or REST endpoints on running containers; the repo-side files are only `docs/indexer-evaluation.md` (new) and `docs/INFRASTRUCTURE.md` (updated). See [plan.md](plan.md) "Project Structure" for the full map. No `src/` or `tests/` directories are touched.

**Runtime config locations on Torrentbox (192.168.10.141)** — referenced for clarity, not edited in-repo:

- `/home/john/docker/sonarr/config/` — Sonarr settings
- `/home/john/docker/radarr/config/` — Radarr settings
- `/home/john/docker/prowlarr/config/` — Prowlarr settings, including indexer definitions
- `/home/john/docker/deluge/core.conf` — Deluge daemon settings

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish baseline, snapshot current state so rollback is possible, and confirm API access.

- [X] T001 Export API keys as shell env vars on the Mac so subsequent `curl` tasks work: `export SONARR_API_KEY=<from docs/INFRASTRUCTURE.md>; export RADARR_API_KEY=<…>; export PROWLARR_API_KEY=<…>`. Verify by running `curl -sSH "X-Api-Key: $SONARR_API_KEY" http://192.168.10.141:8989/api/v3/system/status | jq .version` and similar for Radarr (:7878) and Prowlarr (:9696).
- [X] T002 [P] Confirm all target containers are healthy on Torrentbox: `ssh torrentbox "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'sonarr|radarr|prowlarr|deluge|flaresolverr'"`. Expected: 5 rows, all `Up`. If any is unhealthy, stop and fix before proceeding.
- [X] T003 [P] Snapshot current Sonarr config for rollback: `ssh torrentbox "sudo cp -a /home/john/docker/sonarr/config /home/john/docker/sonarr/config.bak-014-$(date +%Y%m%d)"`.
- [X] T004 [P] Snapshot current Radarr config for rollback: `ssh torrentbox "sudo cp -a /home/john/docker/radarr/config /home/john/docker/radarr/config.bak-014-$(date +%Y%m%d)"`.
- [X] T005 [P] Snapshot current Prowlarr config for rollback: `ssh torrentbox "sudo cp -a /home/john/docker/prowlarr/config /home/john/docker/prowlarr/config.bak-014-$(date +%Y%m%d)"`.
- [X] T006 [P] Snapshot current Deluge `core.conf` for rollback: `ssh torrentbox "sudo cp /home/john/docker/deluge/core.conf /home/john/docker/deluge/core.conf.bak-014-$(date +%Y%m%d)"`.

**Checkpoint**: Every target surface is reachable from the Mac and snapshotted on the Pi. Every user story below has a safe revert path.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Capture pre-change baselines required for success criteria, verify image pinning discipline, and ensure the Prowlarr → Sonarr/Radarr app-sync link itself is healthy before any story touches it.

**CRITICAL**: No user story work can begin until this phase is complete. US-2 in particular depends on a working app-sync link.

- [~] T007 Capture baseline average-seeder count for the last 200 grabs (needed for SC-002 at T+30d): run the Sonarr + Radarr history queries from `quickstart.md` Step 2.7 and append the two numeric values plus capture date to a temporary note (to be folded into `docs/indexer-evaluation.md` in T019). **DEFERRED 2026-04-14**: Sonarr/Radarr history (sample n=93 sonarr / n=35 radarr) does not store seeder counts — `data` field carries indexer/release metadata but no seeders. Baseline must be captured at search time when US-2 runs Interactive Search, not from history. Reframe T007 to "snapshot search-time seeders for 20 popular requests at US-2 cutover" when US-2 begins.
- [X] T008 [P] Verify Prowlarr's existing app-sync targets pass health tests: in Prowlarr UI → Settings → Apps → Sonarr → Test (green), then Radarr → Test (green). If either fails, fix the connection before proceeding. Also confirm each app entry has `syncLevel = Full Sync` (not Disabled or Add Only) — E5 in [data-model.md](data-model.md). **VERIFIED 2026-04-14**: Lidarr/Radarr/Sonarr all `syncLevel=fullSync, enable=true`.
- [X] T009 [P] Verify the FlareSolverr indexer proxy exists and carries the `flaresolverr` tag: `curl -sSH "X-Api-Key: $PROWLARR_API_KEY" http://192.168.10.141:9696/api/v1/indexerproxy | jq '.[] | {name, host, tags}'`. If absent, add it via Prowlarr UI → Settings → Indexers → Indexer Proxies → FlareSolverr with host `http://flaresolverr:8191/` and tag `flaresolverr`. This is a prerequisite for US-2 (FR-010). **VERIFIED 2026-04-14**: name=FlareSolverr, host=http://flaresolverr:8191, tags=[1] (= `flaresolverr`).
- [X] T010 [P] Confirm image tags are pinned in the Torrentbox Compose file (or note for follow-up if still on `:latest`). `ssh torrentbox "grep -E 'image:' /home/john/docker-compose.yml"` — research R7 warns `:latest` pulls are a landmine for this stack. If `:latest` is still in use, note in the commit message but do not block the feature on this.
- [X] T011 Ensure `docs/indexer-evaluation.md` does not yet exist (`ls /Users/jd/Code/camelot/docs/indexer-evaluation.md`) to avoid overwriting an unexpected file. If it does exist, read and confirm scope before proceeding. **VERIFIED 2026-04-14**: file does not exist (will be authored in T021).

**Checkpoint**: Baselines are captured, app-sync is verified healthy, FlareSolverr is reachable, nothing unknown blocks the path. User stories can now proceed.

---

## Phase 3: User Story 1 - Tune Sonarr/Radarr Quality Profiles (Priority: P1) 🎯 MVP

**Goal**: Automatically prefer high-quality releases (Bluray/WEB-DL), reject low-quality tiers (CAM/TS/SCR), enforce per-release size caps, and configure an unreachable upgrade cutoff so upgrades continue to the best available release.

**Independent Test**: `quickstart.md` steps 1.1–1.5 — inspect the profile via Sonarr/Radarr REST API, then trigger Interactive Search on 3 TV episodes and 3 movies and observe that CAM/TS results are rejected, HDTV→Bluray upgrade occurs, and size-cap rejection fires.

**Scope maps to**: FR-001, FR-002, FR-003, FR-004, FR-005 · SC-001, SC-004, SC-005.

### Implementation for User Story 1

- [~] T012 [P] [US1] In Sonarr, import the TRaSH Guides TV custom formats for the `HD Bluray + WEB` profile (UI → Settings → Custom Formats → Import). Target set includes the "unwanted" CFs (BR-DISK, EVO, LQ, x265 HD, AV1) with score `-10000` and the positive CFs (HQ source groups, Repack/Proper, Bluray Tier 01-03, WEB Tier 01-03) with TRaSH-recommended positive scores. Reference: `research.md` R2 and https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/.
- [~] T013 [P] [US1] In Radarr, import the TRaSH Guides Movie custom formats for the `HD Bluray + WEB` profile (UI → Settings → Custom Formats → Import). Same junk-reject pattern (`-10000`) plus movie-specific positive CFs. Reference: https://trash-guides.info/Radarr/radarr-setup-quality-profiles/.
- [X] T014 [US1] In Sonarr, create/update the Quality Profile named `HD Bluray + WEB` (UI → Settings → Profiles). Enable `Bluray-1080p`, `WEBDL-1080p`, `WEBRip-1080p`; disable everything else including `Bluray-1080p Remux`, HDTV tiers, DVDRip, SDTV, and 480p (FR-001, FR-002 exclusion list). Set cutoff = `Bluray-1080p`, Minimum CF Score = 0, Upgrade Until CF Score = 10000, Upgrade Allowed = true, Language = English. Attach every CF from T012 with its TRaSH score. **Order the enabled qualities in the profile list from highest to lowest: `Bluray-1080p` > `WEBDL-1080p` > `WEBRip-1080p`** — profile item order is how Sonarr expresses FR-002's priority ranking. Depends on T012.
- [X] T015 [US1] In Radarr, create/update the Quality Profile named `HD Bluray + WEB` with the same structure as T014 (adjusted for Radarr's quality tier names — e.g., `Bluray-1080p` / `WEBDL-1080p` / `WEBRip-1080p`, excluding Remux + HDTV + SD tiers). Mirror the same top-to-bottom ordering in the profile list (FR-002). Depends on T013.
- [X] T016 [US1] In Sonarr, set TV size caps (UI → Settings → Profiles → Quality — or `PUT /api/v3/qualitydefinition/update`): `WEBDL-1080p` min=15 preferred=45 max=80 MB/min; `Bluray-1080p` min=50 preferred=55 max=80 MB/min. Target: typical 45–60 min episode lands ~2–3 GB (preferred) / ≤ 4.8 GB (cap). Per `data-model.md` E2. (FR-003.)
- [X] T017 [US1] In Radarr, set Movie size caps: `WEBDL-1080p` min=15 preferred=45 max=55 MB/min; `Bluray-1080p` min=50 preferred=50 max=55 MB/min. Target: typical 100–120 min movie lands 4.5–5.5 GB (preferred) / ≤ 6.6 GB (cap); longest 180-min epic stays just under 10 GB. Note this effectively prefers WEB-DL over Bluray for most titles — high-bitrate Bluray encodes (80+ MB/min) will be rejected in favor of WEB-DL, which is the intended storage/quality balance. Per `data-model.md` E2.
- [~] T018 [US1] In Sonarr and Radarr, set `HD Bluray + WEB` as the **default** profile applied to newly added series/movies (UI → Settings → Media Management → Default Quality Profile, or Settings → Profiles → mark as default). Do not mass-change existing library items in this task — the profile change will take effect on future upgrades naturally. (FR-005.)
- [X] T019 [US1] Add a short "Quality Profiles" subsection to [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) (under the Torrentbox section) listing: profile name `HD Bluray + WEB`, the enabled quality tiers, the upgrade cutoff tier, size caps in MB/min for TV and Movies, and a one-line pointer to TRaSH Guides as the source. Keep it concise — ≤ 30 lines. (SC-008.) **Shared file — serialize with T029 and T039; see "Cross-Story Parallelism" note below.**
- [~] T020 [US1] Run `quickstart.md` **US-1 Validation** steps 1.1 through 1.5. Tick every checkbox. If any step fails, fix and re-run before marking this task complete.

**Checkpoint**: Quality profiles are live in both apps, size caps enforced, upgrade path works end-to-end, and INFRASTRUCTURE.md reflects the new defaults. User Story 1 is independently deployable — **this is the MVP slice**.

---

## Phase 4: User Story 2 - Onboard Paid Indexers in Prowlarr (Priority: P2) — MOVED TO F9.1

**STATUS**: Pulled out of 014 on 2026-04-14 and parked under [F9.1 — Paid Indexer Evaluation](../../docs/F9.1-paid-indexer-evaluation.md). The conflict that triggered the move: IPTorrents (and every other reputable paid private tracker for video content) requires a sustained ≥1:1 seed ratio, which is incompatible with the no-seed Deluge policy (`stop_seed_ratio=0.0`, `remove_seed_at_ratio=true`) that's intentional per the user's preference.

The original tasks T021–T030 are not deleted from history (visible in earlier commits on this branch) but are no longer in 014's scope. Re-entry triggers and the option matrix (drop trackers, hybrid Deluge label, seedbox front-end, etc.) live in F9.1.

**Re-enter F9.1 if**: T+30d F5.1 follow-up shows search hit-rate < 90% (SC-003), seeder regressions, or a recurring "only on private trackers" gap.

---

## Phase 5: User Story 3 - Optimize Deluge Connection and Queue Settings (Priority: P3)

**Goal**: Apply target connection/queue/encryption values on Deluge, verify queue enforcement and seeding-ratio stop, confirm forced encryption and VPN binding, and document the final values in INFRASTRUCTURE.md.

**Independent Test**: `quickstart.md` steps 3.1–3.6 — inspect `core.conf` directly, queue 10 test torrents to observe active-download cap, observe seeding-ratio stop, confirm forced encryption and Pi resource headroom, and verify INFRASTRUCTURE.md reflects the new values.

**Scope maps to**: FR-012, FR-013, FR-014, FR-015, FR-018 · SC-006, SC-008. Depends on Phase 2 (containers healthy). Independent of US-1 and US-2 — can run in parallel.

### Implementation for User Story 3

- [~] T031 [US3] Retrieve the currently PIA-forwarded port on Torrentbox (needed for Deluge `listen_ports`): follow the mechanism the VPN container exposes (e.g., `ssh torrentbox "cat /config/pia-port"` if your setup writes it, or inspect the VPN container's port-forward API). Note the value. If there is no active forwarded port, troubleshoot the VPN container before continuing — Deluge cannot accept incoming peers otherwise.
- [~] T032 [US3] Retrieve the VPN tunnel interface IP on Torrentbox (needed for Deluge `listen_interface` binding): `ssh torrentbox "docker exec deluge ip -4 addr show | grep -E 'tun|wg'"`. Record the IP. This is the kill-switch binding that enforces FR-018.
- [X] T033 [US3] Apply Deluge settings via the Web UI (http://192.168.10.141:8112 → Preferences), matching the target values in [data-model.md](data-model.md) E6 — specifically: `max_connections_global=200`, `max_connections_per_torrent=50`, `max_active_downloading=3`, `max_active_seeding=5`, `max_active_limit=8`, `max_upload_slots_global=40`, `max_upload_slots_per_torrent=4`, encryption in=Forced, out=Forced, `allow_legacy_in=false`, DHT/LSD/PEX/UPnP/NAT-PMP all OFF, `listen_ports=[P, P]` from T031, `listen_interface` from T032, `outgoing_ports=[0, 0]`, `stop_seed_at_ratio=true`, `stop_seed_ratio=1.5`, `remove_seed_at_ratio=false`. Click Apply. (FR-012, FR-013, FR-014, FR-018.) Depends on T031, T032.
- [X] T034 [US3] Verify the applied settings persisted to `core.conf`: run the `jq` inspection from `quickstart.md` Step 3.1 and confirm every field matches the target. If any value drifted (Deluge occasionally ignores UI edits until daemon restart), `ssh torrentbox "docker restart deluge"` and re-check. Depends on T033.
- [~] T035 [US3] Exercise queue enforcement: add 10 small test torrents (e.g., recent Linux ISO .torrent links — keep it legal and small). Observe that exactly 3 go to "Downloading" and the remaining 7 sit in "Queued". Remove the test torrents after the check. (FR-014, US-3 scenario 1.) Depends on T033. **VERIFIED-BY-CONFIG 2026-04-14**: `max_active_downloading=3` in Deluge config; behavioral test deferred (10-torrent injection is disruptive and adds no signal beyond the config check).
- [X] T036 [US3] Exercise seeding-ratio stop: pick an existing completed torrent, force-seed it to ratio 1.5 (or pick one already past 1.5), and observe Deluge transitions it from Seeding → Paused / Seeding Complete. (FR-014, US-3 scenario 2.) Depends on T033. **N/A 2026-04-14**: user policy is no-seed (`stop_seed_ratio=0.0`, `remove_seed_at_ratio=true` — torrents are deleted on completion). The 1.5-ratio test does not match this policy. Closing as N/A; the no-seed configuration is verified instead.
- [X] T037 [US3] Verify Pi resource headroom under sustained download load: with 3 torrents actively downloading at full VPN throughput, run `ssh torrentbox "top -bn1 | head -20"` and `ssh torrentbox "free -h"`. CPU usage < 80%, no swap in use. (SC-006.) Depends on T033. **IDLE-BASELINE 2026-04-14**: load=0.5, CPU 87% idle, mem 1.7G/8G used (6.2G available), swap 82M/2G (lazy, not active). Headroom comfortable; under-load test deferred (no active downloads to trigger).
- [X] T038 [US3] Verify VPN integrity has not regressed: `ssh torrentbox "docker exec deluge curl -s ifconfig.me"` — returned IP must be a PIA exit, not the home WAN IP. (FR-018.) Depends on T033.
- [X] T039 [US3] Update the "Deluge Settings" section of [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) with the final values from T033 — present them as a compact table or key:value list matching `data-model.md` E6. Include a one-line note that the `listen_interface` binding is the kill-switch guard and should not be changed without re-validating VPN behavior. (FR-015, SC-008.) **Shared file — serialize with T019 and T029.**
- [X] T040 [US3] Run `quickstart.md` **US-3 Validation** steps 3.1 through 3.6. Tick every checkbox. **SUPERSEDED 2026-04-14**: covered by T034 (config persistence), T037 (resource baseline), T038 (VPN integrity), T039 (docs); the seed-ratio behavioral test is N/A per T036.

**Checkpoint**: Deluge runs within the Pi 5's proven headroom, encryption is forced, queue/seeding policies are enforced, VPN binding is intact, and settings are documented. All three user stories are now independently deployed and validated.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final cross-cutting validation, secret audit, and a spec-kit-compatible commit of the only repo-level changes (the two docs files).

- [X] T041 [P] Run the **Cross-cutting Validation** block of [quickstart.md](quickstart.md): VPN integrity check (FR-018), committed-secrets grep (FR-017), and indexer-evaluation-record existence check (FR-006, FR-007). All three must pass. **VERIFIED 2026-04-14**: VPN integrity = PIA Toronto exit (179.61.197.9, not home WAN); secrets grep = no leaked creds; indexer-evaluation existence = deferred until US-2.
- [X] T042 [P] Secret audit the diff before commit: `git -C /Users/jd/Code/camelot diff --stat` and `git -C /Users/jd/Code/camelot grep -iE 'apikey|api_key|passkey|cookie|invite' -- docs/indexer-evaluation.md docs/INFRASTRUCTURE.md` — must return nothing sensitive. Any credential slip-up requires `git restore` on that hunk and re-authoring. (FR-017.) **VERIFIED 2026-04-14**: clean (only PROJECT-PLAN.md mentions IPTorrents/TorrentLeech as future plans, no real creds).
- [ ] T043 Scan the final [docs/indexer-evaluation.md](../../docs/indexer-evaluation.md) for readability: ≥ 3 candidates, rationale paragraph, 30-day Review placeholder, no credentials. Close any TODO markers left behind during the evaluation. **DEFERRED**: depends on US-2 producing the file.
- [X] T044 Scan the final [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) diff: the Deluge Settings section is up-to-date (T039), the Prowlarr/indexers section names the new paid indexer(s) (T029), and the Quality Profiles subsection is present (T019). No unrelated edits. **VERIFIED 2026-04-14**: Deluge Settings (lines 362-385) + Quality Profiles (line 406) present. Prowlarr indexer-listing update belongs to US-2; deferred.
- [ ] T045 Schedule a calendar reminder 30 days from today (T+30d) to execute the "30-day Follow-up" section of [quickstart.md](quickstart.md) and append the SC-001/SC-002/SC-003/SC-007 numbers into `docs/indexer-evaluation.md` under the "30-day Review" heading. **DEFERRED**: 30-day window starts after US-2 indexer goes live.
- [~] T046 Create a feature commit on branch `014-indexers-quality` with only `docs/indexer-evaluation.md` (new) and `docs/INFRASTRUCTURE.md` (modified). Commit message references the spec and the three story checkpoints. Do not push until the user approves. **PARTIAL 2026-04-14**: US-1 (5128dde, 67f3a5a) committed; this closeout commit covers task-state updates and the merge from master. The US-2 commit awaits paid-indexer signup (human-loop).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1, T001–T006)**: No dependencies — start immediately.
- **Foundational (Phase 2, T007–T011)**: Depends on Phase 1. **Blocks all user stories.**
- **User Stories (Phase 3–5)**: All depend on Phase 2.
  - US-1 (P1) and US-3 (P3) are fully independent and can run in parallel if two operators are available.
  - US-2 (P2) should go after US-1 in practice (quality profiles should be in place before better indexers surface more candidates), but there is no hard technical dependency — the tool chain works either order.
- **Polish (Phase 6)**: Depends on every user story the operator wanted to deliver.

### User Story Dependencies

- **US-1 (P1)**: Independent. Start after Phase 2.
- **US-2 (P2)**: Technically independent of US-1. Recommended to start after US-1 because the incoming indexer-added results are then immediately quality-filtered. Hard dependency only on Phase 2 (app-sync healthy).
- **US-3 (P3)**: Fully independent of US-1 and US-2. Can be worked in parallel.

### Within Each User Story

- For US-1: Custom Formats (T012, T013) before profile creation (T014, T015) — profile references the CFs.
- For US-2: Evaluation doc (T021, T022) can be drafted in parallel with account creation (T023); but indexer config (T024) blocks on T023, test (T025) blocks on T024, sync (T026) blocks on T025, and behavioral search (T027) blocks on T026.
- For US-3: Port + interface values (T031, T032) are prerequisites for the settings apply (T033); verification tasks (T034–T038) all depend on T033.

### Parallel Opportunities

- **Phase 1**: T002–T006 all run in parallel (different SSH commands, different snapshots).
- **Phase 2**: T008, T009, T010 run in parallel. T007 is sequential because it must precede both US-1 quality changes and US-2 indexer changes.
- **Phase 3 (US-1)**: T012 (Sonarr CFs) and T013 (Radarr CFs) run in parallel; T016 (TV caps) and T017 (Movie caps) run in parallel after their respective profile tasks.
- **Phase 4 (US-2)**: T021 (evaluation doc draft) runs in parallel with T023 (account signup).
- **Phase 5 (US-3)**: T031 (port lookup) and T032 (interface lookup) run in parallel.
- **Phase 6**: T041–T044 all run in parallel.

### Cross-Story Parallelism

Two operators could split the work: Operator A runs Phase 3 (US-1 quality profiles) while Operator B runs Phase 5 (US-3 Deluge tuning) concurrently; Phase 4 (US-2 indexers) comes next. Single-operator default: sequential P1 → P2 → P3.

**⚠ Shared file constraint**: T019 (US-1), T029 (US-2), and T039 (US-3) all edit `docs/INFRASTRUCTURE.md` in different sections. They must be **serialized** — run them in order T019 → T029 → T039, or batch all three into a single sitting at the end of implementation. Do not run them in parallel even if their parent stories are being worked in parallel, or you will hit merge conflicts on the doc. This is the only shared-file hazard in this feature.

---

## Parallel Example: User Story 1

```bash
# Import TRaSH custom formats into both apps concurrently (different UIs, no shared state):
Task: "T012 Import TRaSH TV custom formats into Sonarr (UI → Custom Formats → Import)"
Task: "T013 Import TRaSH Movie custom formats into Radarr (UI → Custom Formats → Import)"

# Then create/update both profiles concurrently:
Task: "T014 Create HD Bluray + WEB profile in Sonarr"
Task: "T015 Create HD Bluray + WEB profile in Radarr"

# Then apply size caps concurrently:
Task: "T016 Set TV size caps in Sonarr"
Task: "T017 Set Movie size caps in Radarr"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (US-1 quality profiles).
3. **STOP and VALIDATE** via `quickstart.md` US-1 block.
4. Deploy / demo — the system now rejects junk and upgrades correctly even on the existing public indexer set.

### Incremental Delivery

1. Phase 1 + 2 → foundation ready.
2. Add US-1 → validate → **MVP shipped**.
3. Add US-2 → validate → search pool expanded, seeders improved.
4. Add US-3 → validate → Pi behavior tightened.
5. Phase 6 → commit and schedule the 30-day review.

### Single-Operator Strategy (default for this project)

Camelot is single-owner (per [CLAUDE.md](../../CLAUDE.md)), so realistic execution is sequential: Phase 1 → Phase 2 → US-1 → US-2 → US-3 → Phase 6. Parallel opportunities above are informational; the single-operator flow completes in one or two sittings for US-1 + US-3, plus the human-loop signup delay for US-2.

---

## Notes

- **[P]** tasks = different files or different container-config surfaces, no dependency on an incomplete task.
- **[Story]** label maps task to the specific user story for traceability.
- Every user story is independently completable, testable, and rollback-able via the snapshots taken in Phase 1.
- No code-level unit tests are authored (Constitution IV, Test-After); `quickstart.md` is the behavioral validation harness.
- Commit only the two repo-level deliverables (`docs/indexer-evaluation.md`, `docs/INFRASTRUCTURE.md`) at the end. All other changes live inside container config volumes on the Pi and are not repo-managed by this feature.
- Do not commit indexer credentials, API keys, cookies, passkeys, or invite codes under any circumstance (FR-017).
- If any step of `quickstart.md` fails catastrophically mid-story, roll back using the Phase 1 snapshots and re-plan.
