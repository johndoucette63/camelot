# Tasks: Device Enrichment & Auto-Identification

**Input**: Design documents from `/specs/013-device-enrichment/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the feature specification. Test tasks are omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `advisor/backend/` (FastAPI), `advisor/frontend/src/` (React)

---

## Phase 1: Setup

**Purpose**: Add new dependency and create database migration

- [x] T001 [P] Add `zeroconf>=0.132` to `advisor/backend/requirements.txt`
- [x] T002 [P] Create Alembic migration `advisor/backend/migrations/versions/007_device_enrichment.py` — add 8 columns to `devices` (os_family, os_detail, mdns_name, netbios_name, ssdp_friendly_name, ssdp_model, last_enriched_at, enrichment_ip), add 2 columns to `annotations` (classification_source, classification_confidence), backfill classification_source='user' for existing annotations where role != 'unknown'

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extend models, API schemas, and create enrichment scaffold. MUST complete before any user story.

- [x] T003 [P] Add enrichment columns to Device model in `advisor/backend/app/models/device.py` — os_family (String 50), os_detail (String 255), mdns_name (String 255), netbios_name (String 255), ssdp_friendly_name (String 255), ssdp_model (String 255), last_enriched_at (DateTime), enrichment_ip (String 15), all nullable
- [x] T004 [P] Add classification columns to Annotation model in `advisor/backend/app/models/annotation.py` — classification_source (String 50, nullable), classification_confidence (String 10, nullable)
- [x] T005 [P] Extend DeviceOut and AnnotationOut Pydantic schemas in `advisor/backend/app/routers/devices.py` — add os_family, os_detail, mdns_name, netbios_name, ssdp_friendly_name, ssdp_model, last_enriched_at to DeviceOut; add classification_source, classification_confidence to AnnotationOut; update _device_to_out() mapper
- [x] T006 [P] Extend Device and Annotation TypeScript interfaces in `advisor/frontend/src/types.ts` — add os_family, os_detail, mdns_name, netbios_name, ssdp_friendly_name, ssdp_model, last_enriched_at to Device; add classification_source, classification_confidence to Annotation
- [x] T007 Create enrichment orchestrator scaffold in `advisor/backend/app/services/enrichment.py` — define async run_enrichment(db, mdns_cache) function that queries devices needing enrichment (last_enriched_at IS NULL or enrichment_ip != ip_address), calls enrichment sources (stub functions initially), updates last_enriched_at and enrichment_ip after processing
- [x] T008 Integrate run_enrichment() into scanner loop in `advisor/backend/scanner_entrypoint.py` — import and call run_enrichment(db, mdns_cache) after run_scan() completes (after line 93), pass mDNS cache dict, log enrichment start/finish with structured JSON

**Checkpoint**: Foundation ready — enrichment scaffold runs (no-op) after each scan cycle. API returns new null fields. Frontend types updated.

---

## Phase 3: User Story 1 — Passive mDNS Discovery (Priority: P1)

**Goal**: Apple devices, printers, speakers, and smart home gear are automatically identified by their mDNS/Bonjour service advertisements without any active probing.

**Independent Test**: Run scanner, verify devices advertising mDNS services appear in the inventory with their advertised name and a role derived from their service type.

### Implementation for User Story 1

- [x] T009 [US1] Implement MdnsListener class in `advisor/backend/app/services/enrichment.py` — create a class that wraps zeroconf.Zeroconf + ServiceBrowser for key service types (_airplay._tcp, _companion-link._tcp, _ipp._tcp, _printer._tcp, _homekit._tcp, _sonos._tcp, _http._tcp, _smb._tcp, _raop._tcp, _googlecast._tcp), stores discoveries in a thread-safe dict keyed by IP address, with start() and close() methods
- [x] T010 [US1] Implement mDNS name parsing in `advisor/backend/app/services/enrichment.py` — add parse_mdns_name() function that strips service type suffixes (e.g., `._companion-link._tcp.local.`), replaces hyphens/underscores with spaces, returns a clean friendly name (e.g., "Johns-iPhone._companion-link._tcp.local." -> "Johns iPhone")
- [x] T011 [US1] Start MdnsListener at scanner boot in `advisor/backend/scanner_entrypoint.py` — instantiate MdnsListener before the scan loop, pass its cache dict to run_enrichment(), call listener.close() on shutdown (KeyboardInterrupt)
- [x] T012 [US1] Implement _enrich_mdns() in `advisor/backend/app/services/enrichment.py` — read from the mDNS cache dict, match entries to devices by IP address, update device.mdns_name with parsed friendly name, store raw service types for classification use, skip devices that already have an mdns_name and haven't changed IP

**Checkpoint**: After a scan cycle, Apple devices and mDNS-advertising devices show their friendly names in the inventory.

---

## Phase 4: User Story 2 — Active OS/Service Fingerprinting (Priority: P2)

**Goal**: Devices that don't advertise via mDNS are identified through targeted nmap OS detection, service scanning, and NetBIOS name resolution.

**Independent Test**: Place a device without mDNS (e.g., Linux server) on the network, run enrichment, verify OS family, open services, and optionally NetBIOS name appear on the device record.

### Implementation for User Story 2

- [x] T013 [US2] Implement _enrich_nmap() in `advisor/backend/app/services/enrichment.py` — select up to 5 devices needing fingerprinting (no hostname or no os_family, not already enriched), run nmap scan with flags `-O -sV --top-ports 100 --host-timeout 30s --script nbstat.nse`, extract OS family and OS detail from nmap results, extract NetBIOS name from NSE script output
- [x] T014 [US2] Implement device selection and rate-limiting logic in `advisor/backend/app/services/enrichment.py` — query devices where (hostname IS NULL OR os_family IS NULL) AND (last_enriched_at IS NULL OR enrichment_ip != ip_address), limit to 5 per cycle, order by last_enriched_at ASC NULLS FIRST (prioritize never-enriched devices)
- [x] T015 [US2] Implement service upsert from nmap results in `advisor/backend/app/services/enrichment.py` — for each detected open port/service from nmap, upsert into the services table using the existing (device_id, name) unique constraint, set port and status fields

**Checkpoint**: After several scan cycles, devices without mDNS show OS family, open services, and NetBIOS names.

---

## Phase 5: User Story 3 — Auto-Classify Device Roles (Priority: P3)

**Goal**: Devices are automatically assigned meaningful roles (printer, speaker, server, etc.) based on enrichment data, while never overwriting user-set roles.

**Independent Test**: Enrich devices via any method, verify classification engine assigns appropriate roles with correct confidence levels.

### Implementation for User Story 3

- [x] T016 [US3] Implement classification rules dict in `advisor/backend/app/services/enrichment.py` — define MDNS_ROLE_MAP (service type -> role + confidence), PORT_ROLE_MAP (port -> role + confidence), OS_ROLE_MAP (os_family -> role + confidence), VENDOR_ROLE_MAP (vendor substring -> role + confidence) per research.md classification table
- [x] T017 [US3] Implement _auto_classify() in `advisor/backend/app/services/enrichment.py` — for each device with enrichment data, evaluate classification rules in priority order (mDNS > ports > OS > vendor), assign role to annotation if classification_source is not "user", set classification_source and classification_confidence, create annotation if none exists (default role="unknown")
- [x] T018 [US3] Update PATCH annotation endpoint to set classification_source="user" in `advisor/backend/app/routers/devices.py` — when a user sets a role via PATCH /devices/{mac}/annotation, also set annotation.classification_source = "user" and annotation.classification_confidence = None to prevent auto-classification from overwriting

**Checkpoint**: Devices are auto-classified with roles like "printer", "speaker", "server". User-set roles are preserved.

---

## Phase 6: User Story 4 — SSDP/UPnP Discovery (Priority: P4)

**Goal**: Smart TVs, media players, and UPnP-enabled devices are identified with their friendly names and model information.

**Independent Test**: Have a UPnP device on the network, run enrichment, verify friendly name and model info appear on the device record.

### Implementation for User Story 4

- [x] T019 [US4] Implement SSDP M-SEARCH sender in `advisor/backend/app/services/enrichment.py` — send UDP multicast M-SEARCH to 239.255.255.250:1900 with ST=ssdp:all and MX=5, collect responses for 10 seconds, parse LOCATION headers from responses
- [x] T020 [US4] Implement UPnP XML description fetcher in `advisor/backend/app/services/enrichment.py` — for each SSDP responder, fetch the device description XML from the LOCATION URL using httpx with a 5-second timeout, parse friendlyName, manufacturer, modelName, modelNumber using xml.etree.ElementTree
- [x] T021 [US4] Implement _enrich_ssdp() in `advisor/backend/app/services/enrichment.py` — orchestrate M-SEARCH + XML fetch, match responses to existing devices by IP address, update device.ssdp_friendly_name and device.ssdp_model, combine modelName + modelNumber for ssdp_model field

**Checkpoint**: UPnP-capable devices show their friendly names and model info in the inventory.

---

## Phase 7: User Story 5 — View Enrichment Data in Inventory (Priority: P5)

**Goal**: Enrichment metadata (OS, names, classification confidence) is visible in the device table and detail views. Auto-classified roles are visually distinguished from user-set roles.

**Independent Test**: Open device inventory, verify OS column appears, auto-classified roles show "(auto)" indicator, and clicking a device shows enrichment detail section.

### Implementation for User Story 5

- [x] T022 [P] [US5] Add "OS" column to device table in `advisor/frontend/src/components/DeviceTable.tsx` — add a new column after "Vendor" that displays os_family, falling back to "—" if null
- [x] T023 [P] [US5] Add auto-classification badge to role column in `advisor/frontend/src/components/DeviceTable.tsx` — when annotation.classification_source is not "user" and not null, display a small "(auto)" suffix or badge next to the role name in a muted style
- [x] T024 [US5] Add enrichment detail section to device modal in `advisor/frontend/src/components/DeviceAnnotationModal.tsx` — add an "Identification" section showing: OS family + detail, mDNS name, NetBIOS name, SSDP friendly name + model, classification source + confidence, last enriched timestamp; group under a collapsible or tabbed section
- [x] T025 [US5] Add enrichment fields to global filter in `advisor/frontend/src/components/DeviceTable.tsx` — extend the globalFilterFn to also search os_family, mdns_name, netbios_name, and ssdp_friendly_name

**Checkpoint**: Device inventory shows OS data, auto-classification indicators, and enrichment details on click.

---

## Phase 8: User Story 6 — Trigger Re-Enrichment (Priority: P6)

**Goal**: Admin can trigger re-enrichment for a specific device via a "Re-scan" button, and devices with changed IPs are automatically re-enriched.

**Independent Test**: Click re-scan on a previously enriched device, verify it gets re-enriched on the next scan cycle.

### Implementation for User Story 6

- [x] T026 [P] [US6] Add POST /devices/{mac_address}/re-enrich endpoint in `advisor/backend/app/routers/devices.py` — look up device by MAC, return 404 if not found, set device.last_enriched_at = None, commit, return 202 with message "Device queued for re-enrichment"
- [x] T027 [P] [US6] Add re-scan button to device table in `advisor/frontend/src/components/DeviceTable.tsx` — add a small "Re-scan" button (or refresh icon) in the actions area of each row, calls onRescan callback with the device, use stopPropagation to prevent row click
- [x] T028 [US6] Wire re-scan handler in `advisor/frontend/src/pages/Devices.tsx` — implement handleRescan function that POSTs to /api/devices/{mac}/re-enrich, then refetches the device list; pass as onRescan prop to DeviceTable

**Checkpoint**: Admin can trigger re-scan per device. Devices with changed IPs are automatically re-enriched.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T029 Add enrichment fields to AI context endpoint in `advisor/backend/app/routers/ai_context.py` — extend AiContextDevice to include os_family and classification_source so the AI advisor has enrichment data for chat context
- [x] T030 Run quickstart.md validation — deploy to HOLYGRAIL via `bash scripts/deploy-advisor.sh`, apply migration, verify scanner logs show enrichment activity, verify API returns enrichment fields, verify frontend displays enrichment data per quickstart.md steps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Phase 2 completion
  - US1 (mDNS) and US2 (nmap) and US4 (SSDP) can proceed in parallel — they are independent enrichment sources
  - US3 (classification) benefits from US1/US2/US4 data but can be implemented independently (will just classify based on whatever data exists)
  - US5 (frontend display) can proceed in parallel with US1-US4 (shows null data until enrichment runs)
  - US6 (re-enrich) is independent of all other stories
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1) mDNS**: After Phase 2 — No story dependencies
- **US2 (P2) nmap**: After Phase 2 — No story dependencies
- **US3 (P3) classify**: After Phase 2 — Independent but most valuable after US1/US2 provide data
- **US4 (P4) SSDP**: After Phase 2 — No story dependencies
- **US5 (P5) frontend**: After Phase 2 — Independent but most useful after US1-US4 provide data
- **US6 (P6) re-enrich**: After Phase 2 — No story dependencies

### Within Each User Story

- Models/schemas completed in Phase 2 (shared foundation)
- Services before endpoints
- Backend before frontend (where both exist)

### Parallel Opportunities

- T001 and T002 can run in parallel (different files)
- T003, T004, T005, T006 can all run in parallel (different files)
- T007 depends on T003, T004 (needs model columns)
- T008 depends on T007 (needs enrichment module)
- US1 (T009-T012), US2 (T013-T015), US4 (T019-T021) can proceed in parallel after Phase 2
- T022 and T023 can run in parallel (same file but independent column definitions — could be combined)
- T026 and T027 can run in parallel (backend vs. frontend)

---

## Parallel Example: User Story 1 (mDNS) + User Story 2 (nmap)

```text
# After Phase 2 completes, launch both in parallel:

# Stream 1 — US1 mDNS:
Task: T009 "Implement MdnsListener class in enrichment.py"
Task: T010 "Implement mDNS name parsing in enrichment.py"
Task: T011 "Start MdnsListener at scanner boot in scanner_entrypoint.py"
Task: T012 "Implement _enrich_mdns() in enrichment.py"

# Stream 2 — US2 nmap (can run simultaneously):
Task: T013 "Implement _enrich_nmap() in enrichment.py"
Task: T014 "Implement device selection and rate-limiting in enrichment.py"
Task: T015 "Implement service upsert from nmap results in enrichment.py"
```

Note: Both streams write to enrichment.py but to different functions — no conflicts.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T008)
3. Complete Phase 3: User Story 1 — mDNS (T009-T012)
4. **STOP and VALIDATE**: Verify mDNS-advertising devices are identified in the inventory
5. Deploy if ready — this alone eliminates most "unknown" devices on a typical home network

### Incremental Delivery

1. Setup + Foundational -> Foundation ready
2. Add US1 (mDNS) -> Passive identification working -> Deploy (MVP)
3. Add US3 (classify) -> Auto-roles from mDNS data -> Deploy
4. Add US2 (nmap) -> Deeper fingerprinting for remaining unknowns -> Deploy
5. Add US4 (SSDP) -> UPnP device discovery -> Deploy
6. Add US5 (frontend) -> Enrichment data visible in UI -> Deploy
7. Add US6 (re-enrich) -> Manual re-scan capability -> Deploy
8. Polish -> AI context, quickstart validation -> Deploy

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All enrichment sources (US1, US2, US4) write to the same file (enrichment.py) but different functions — no merge conflicts if implemented sequentially
- The scanner container already runs with host networking and root privileges — no Docker changes needed
- The existing services table is reused for nmap-discovered ports — no new table needed
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
