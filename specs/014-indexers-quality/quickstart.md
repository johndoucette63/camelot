# Quickstart: Indexers & Quality Optimization

**Feature**: 014-indexers-quality
**Date**: 2026-04-14
**Purpose**: End-to-end validation procedure. Run this after implementation to confirm the feature meets its spec.

This quickstart doubles as the Test-After harness (per Constitution IV). Each step maps to specific requirements and/or success criteria.

> **Scope**: Torrentbox Pi 5 (192.168.10.141). All commands run from the Mac workstation unless noted.

---

## Prerequisites

- [ ] SSH reachability: `ssh torrentbox "uptime"` succeeds.
- [ ] `curl` + `jq` installed on the Mac.
- [ ] API keys for Sonarr (`SONARR_API_KEY`), Radarr (`RADARR_API_KEY`), Prowlarr (`PROWLARR_API_KEY`) available from `docs/INFRASTRUCTURE.md` and exported as env vars in the current shell.
- [ ] All containers healthy:
  ```bash
  ssh torrentbox "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'sonarr|radarr|prowlarr|deluge|flaresolverr'"
  ```
  Expected: all five running, all `Up (healthy)` or `Up N minutes`.

---

## US-1 Validation: Quality Profiles (P1)

**Goal**: Confirm Sonarr/Radarr reject low-quality releases, prefer Bluray/WEB-DL, upgrade across tiers, and enforce size caps.

### Step 1.1 — Inspect the Sonarr profile

```bash
curl -sSH "X-Api-Key: $SONARR_API_KEY" \
  http://192.168.10.141:8989/api/v3/qualityprofile \
  | jq '.[] | select(.name=="HD Bluray + WEB") | {name, cutoff: .cutoff, cutoffFormatScore, minFormatScore}'
```

Expected output:

```json
{
  "name": "HD Bluray + WEB",
  "cutoff": <id of Bluray-1080p>,
  "cutoffFormatScore": 10000,
  "minFormatScore": 0
}
```

- [ ] **PASS** if profile exists with `cutoffFormatScore = 10000` and `minFormatScore = 0`. → FR-002, FR-004.
- [ ] **FAIL** → profile missing or misconfigured; revisit implementation.

### Step 1.2 — Inspect size caps

```bash
curl -sSH "X-Api-Key: $SONARR_API_KEY" \
  http://192.168.10.141:8989/api/v3/qualitydefinition \
  | jq '.[] | select(.quality.name=="WEBDL-1080p" or .quality.name=="Bluray-1080p") | {quality: .quality.name, minSize, maxSize}'
```

- [ ] **PASS** for TV if `WEBDL-1080p` = `{min:15, preferred:45, max:80}` and `Bluray-1080p` = `{min:50, preferred:55, max:80}` MB/min. → FR-003.
- [ ] Repeat with `$RADARR_API_KEY` on `:7878` for movies; expect `WEBDL-1080p` = `{min:15, preferred:45, max:55}` and `Bluray-1080p` = `{min:50, preferred:50, max:55}` MB/min. Caps are chosen so every grab lands under 10 GB and typical runtimes fall in the 3–6 GB band. → FR-003.

### Step 1.3 — Behavioral: low-quality rejection

1. Pick a popular recent TV episode already in Sonarr's library.
2. In Sonarr UI → the series → Interactive Search.
3. Observe the results list.

- [ ] **PASS** if every CAM/TS/TC/SCR result is marked rejected (red badge) with reason "quality not wanted" or similar. → FR-001, US-1 scenario 1.

### Step 1.4 — Behavioral: upgrade path

1. In Sonarr, find an episode that currently has a WEBDL-720p or HDTV-720p file.
2. Trigger Interactive Search and manually grab a Bluray-1080p release if available.

- [ ] **PASS** if Sonarr accepts the grab, downloads it via Deluge, imports it, and deletes/replaces the earlier file. → FR-004, US-1 scenario 2.

### Step 1.5 — Behavioral: size cap rejection

1. In Radarr, Interactive Search a movie where a 4K Remux (40 GB+) exists among results.
2. Inspect the Remux row.

- [ ] **PASS** if the result is rejected with reason "exceeds maximum size" or is absent entirely from selected grabs. → FR-003, US-1 scenario 4.

---

## US-2 Validation: Paid Indexers in Prowlarr (P2)

**Goal**: Confirm the selected paid indexer(s) are configured, tested, synced to Sonarr + Radarr, routed through FlareSolverr where applicable, and observably healthy.

### Step 2.1 — Indexer present and tested

```bash
curl -sSH "X-Api-Key: $PROWLARR_API_KEY" \
  http://192.168.10.141:9696/api/v1/indexer \
  | jq '.[] | select(.name=="IPTorrents") | {name, enable, priority, tags, implementation}'
```

- [ ] **PASS** if IPTorrents appears, `enable=true`, tags include `tv` and `movies` (add `flaresolverr` if gated). → FR-008.

### Step 2.2 — Run Prowlarr's built-in test

In Prowlarr UI → Indexers → click the new indexer → "Test".

- [ ] **PASS** if the test completes green.
- [ ] **FAIL** → check Prowlarr logs; likely causes are wrong cookie/API key, missing FlareSolverr tag, rate limit.

### Step 2.3 — App-sync to Sonarr + Radarr

```bash
curl -sSH "X-Api-Key: $SONARR_API_KEY" \
  http://192.168.10.141:8989/api/v3/indexer \
  | jq '.[] | select(.name=="IPTorrents") | {name, enable, managed: (.configContract=="NewznabSettings")}'

curl -sSH "X-Api-Key: $RADARR_API_KEY" \
  http://192.168.10.141:7878/api/v3/indexer \
  | jq '.[] | select(.name=="IPTorrents") | {name, enable}'
```

- [ ] **PASS** if IPTorrents appears in both Sonarr and Radarr with `enable=true`. → FR-009, US-2 scenario 3.
- [ ] Visual check: open Sonarr and Radarr UIs → Settings → Indexers → IPTorrents shows the Prowlarr badge (read-only marker).

### Step 2.4 — CloudFlare / FlareSolverr path

For a CloudFlare-gated indexer (if one is in the roster):

```bash
curl -sSH "X-Api-Key: $PROWLARR_API_KEY" \
  http://192.168.10.141:9696/api/v1/indexerproxy \
  | jq '.[] | {name, implementation, tags}'
```

- [ ] **PASS** if exactly one FlareSolverr proxy exists with the `flaresolverr` tag, and every CF-gated indexer carries that tag. → FR-010, US-2 scenario 4.

### Step 2.5 — Health surface

In Prowlarr UI → System → Health → click through to each indexer.

- [ ] **PASS** if the new indexer shows OK (not Warning or Error). → FR-011.

### Step 2.6 — Behavioral: search hits a new source

1. In Sonarr, Interactive Search a fresh episode.
2. In Radarr, Interactive Search a fresh movie.
3. Inspect the "Indexer" column.

- [ ] **PASS** if at least one result per search originates from IPTorrents. → US-2 scenario 3, feeds SC-003.

### Step 2.7 — Baseline capture for success criteria

Record these numbers the day the paid indexer goes live so SC-002 and SC-003 can be compared at T+30 days:

```bash
curl -sSH "X-Api-Key: $SONARR_API_KEY" \
  "http://192.168.10.141:8989/api/v3/history?pageSize=200&sortKey=date&sortDirection=descending" \
  | jq '[.records[] | select(.eventType=="grabbed") | .data.seeders // 0 | tonumber] | add / length'
```

- [ ] **PASS** if a baseline average-seeder value is captured and written into the end of `docs/indexer-evaluation.md`. → SC-002.

---

## US-3 Validation: Deluge Tuning (P3)

**Goal**: Confirm connection limits, forced encryption, and queue/seeding policy are applied on the Torrentbox Pi 5, and documented in INFRASTRUCTURE.md.

### Step 3.1 — Inspect `core.conf`

```bash
ssh torrentbox "cat /home/john/docker/deluge/core.conf" \
  | jq '{max_connections_global, max_connections_per_torrent, max_active_downloading, max_active_seeding, max_active_limit, enc_in_policy, enc_out_policy, enc_allow_legacy, dht, lsd, utpex, upnp, natpmp, listen_ports, listen_interface, stop_seed_at_ratio, stop_seed_ratio}'
```

Expected (matches data-model.md E6):

```json
{
  "max_connections_global": 200,
  "max_connections_per_torrent": 50,
  "max_active_downloading": 3,
  "max_active_seeding": 5,
  "max_active_limit": 8,
  "enc_in_policy": 2,
  "enc_out_policy": 2,
  "enc_allow_legacy": false,
  "dht": false,
  "lsd": false,
  "utpex": false,
  "upnp": false,
  "natpmp": false,
  "listen_ports": [<PIA port>, <PIA port>],
  "listen_interface": "<VPN tun IP>",
  "stop_seed_at_ratio": true,
  "stop_seed_ratio": 1.5
}
```

- [ ] **PASS** if all values match. → FR-012, FR-013, FR-014.

### Step 3.2 — Queue enforcement

1. Queue 10 torrents in Deluge (test torrents — small, legal, e.g., Linux ISOs).
2. Watch the active-download count in the Web UI.

- [ ] **PASS** if exactly 3 torrents move to "Downloading" and 7 stay "Queued". → FR-014, US-3 scenario 1.

### Step 3.3 — Seeding ratio stop

1. Pick a completed torrent with ratio already > 1.5 (or pick one, force-seed to 1.5).
2. Observe state.

- [ ] **PASS** if Deluge transitions it to "Paused" / "Seeding Complete" when ratio hits 1.5. → FR-014, US-3 scenario 2.

### Step 3.4 — Forced encryption

1. On the Pi: `ssh torrentbox "docker exec deluge deluge-console 'info'"` and confirm peer connections list shows ⓘ (encrypted) markers for active peers.
2. Alternatively inspect `enc_in_policy=2, enc_out_policy=2` in core.conf.

- [ ] **PASS**. → FR-013, US-3 scenario 3.

### Step 3.5 — Pi resource headroom

While 3 torrents are actively downloading at full VPN throughput:

```bash
ssh torrentbox "top -bn1 | head -20"
ssh torrentbox "free -h"
```

- [ ] **PASS** if CPU usage < 80% sustained and no swap use. → SC-006, US-3 acceptance.

### Step 3.6 — Documentation

```bash
grep -n "Deluge Settings" /Users/jd/Code/camelot/docs/INFRASTRUCTURE.md
```

- [ ] **PASS** if the Deluge Settings section exists and lists every value from Step 3.1. → FR-015, US-3 scenario 4, SC-008.

---

## Cross-cutting Validation

### VPN integrity check (FR-018)

```bash
ssh torrentbox "docker exec deluge curl -s ifconfig.me"
```

- [ ] **PASS** if the returned IP is a PIA exit, not the home WAN IP.

### No committed secrets (FR-017)

```bash
git -C /Users/jd/Code/camelot grep -iE "iptorrents|torrentleech" -- ':(exclude)specs/**' ':(exclude)docs/F5.1-indexers-and-quality.md' || true
git -C /Users/jd/Code/camelot grep -iE "apikey|api_key|cookie|passkey" -- 'docs/indexer-evaluation.md' || echo "no creds committed"
```

- [ ] **PASS** if no API keys, passkeys, or cookies appear in `docs/indexer-evaluation.md` or anywhere else in the repo.

### Indexer evaluation record exists (FR-006, FR-007)

```bash
ls -la /Users/jd/Code/camelot/docs/indexer-evaluation.md
```

- [ ] **PASS** if the file exists, documents ≥ 3 candidates, and includes a selection rationale paragraph.

---

## 30-day Follow-up (recorded, not blocking)

These map to success criteria that require a time window:

- **T+30d**: Recompute average seeders on grabs (Step 2.7 query). Compare to baseline.
  - **SC-002**: Average up ≥ 50%.
- **T+30d**: Tally search hit rate — for 20 mainstream requests, fraction with ≥ 1 acceptable release.
  - **SC-003**: ≥ 90%.
- **T+30d**: Inspect Sonarr/Radarr history for grabbed qualities.
  - **SC-001**: 100% WEB-DL or higher, zero CAM/TS/SCR.
- **T+30d**: Scroll Prowlarr's indexer history for the new indexer.
  - **SC-007**: Healthy ≥ 95% of the window.

Record results in `docs/indexer-evaluation.md` under a "30-day Review" heading.

---

## Rollback

If any step fails catastrophically:

1. **Quality profile**: revert in Sonarr/Radarr UI to the previous profile name or restore from `/home/john/docker/{sonarr,radarr}/config/config.xml` backup.
2. **Indexer**: delete in Prowlarr → forces re-sync → disappears from Sonarr/Radarr.
3. **Deluge**: revert `core.conf` values in the Web UI → Preferences → Apply. The Pi restart is not required.

Every change is reversible in-place. No data migration, no downtime beyond a container restart at worst.
