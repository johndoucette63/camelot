# Feature Specification: Plex Media Server Migration

**Feature Branch**: `004-plex-migration`  
**Created**: 2026-04-07  
**Status**: Draft  
**Input**: User description: "Migrate Plex (and optionally Emby) from Media Server Pi to HOLYGRAIL with NVENC transcoding"

## Clarifications

### Session 2026-04-07

- Q: Migration strategy — parallel run or hard cutover? → A: Parallel run. Keep Pi Plex running during validation, then cut over after confirming HOLYGRAIL is fully functional.
- Q: Remote access — LAN-only or external streaming? → A: Remote access enabled. Plex accessible both on LAN and remotely via Plex account.
- Q: Metadata migration — migrate DB or fresh scan? → A: Fresh scan. Rebuild libraries from NAS mounts, rely on Plex account sync for watch history.
- Q: Torrent pipeline — update Sonarr/Radarr to point at new Plex? → A: In scope. Update Sonarr/Radarr connection settings on Torrentbox to point at HOLYGRAIL Plex.
- Q: Emby leaning — keep, retire, or defer? → A: Leaning retire. Plan to decommission Emby and document rationale; simplifies operations and frees HOLYGRAIL resources for Plex and Ollama.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - GPU-Accelerated Plex on HOLYGRAIL (Priority: P1)

A media consumer wants to stream content from Plex running on HOLYGRAIL, where the RTX 2070 Super provides hardware-accelerated transcoding. Currently, Plex runs on a Raspberry Pi 5, which struggles with transcoding multiple streams or high-bitrate content. By moving to HOLYGRAIL, transcoding is offloaded to the GPU's NVENC encoder, eliminating CPU bottlenecks and enabling smooth playback for all users.

**Why this priority**: This is the core value proposition of the migration — without GPU transcoding working, there's no reason to move Plex off the Pi.

**Independent Test**: Can be fully tested by deploying Plex on HOLYGRAIL, playing a media file that requires transcoding, and confirming the GPU is handling the transcode (visible in Plex dashboard under Settings > Transcoder).

**Acceptance Scenarios**:

1. **Given** Plex is deployed on HOLYGRAIL with GPU access, **When** a user plays a media file that requires transcoding (e.g., 4K HEVC to 1080p H.264), **Then** the Plex dashboard shows "(hw)" hardware transcoding is active and playback is smooth with no buffering.
2. **Given** Plex is running on HOLYGRAIL, **When** the server is rebooted, **Then** Plex automatically restarts and is accessible without manual intervention.
3. **Given** Plex is running on HOLYGRAIL, **When** a user navigates to the Plex web interface, **Then** the interface loads and is fully functional.

---

### User Story 2 - Seamless Library and Metadata Migration (Priority: P1)

A media consumer wants all their existing Plex libraries, watch history, on-deck items, and metadata preserved after migration. The NAS SMB shares that hold media files must be mounted on HOLYGRAIL so Plex can access the same content. The experience should be seamless — no need to re-scan libraries from scratch or lose progress on partially watched shows.

**Why this priority**: Equal to P1 because GPU transcoding is useless if the media libraries aren't accessible or watch history is lost — users would perceive the migration as a regression.

**Independent Test**: Can be tested by mounting NAS shares on HOLYGRAIL, pointing Plex at them, and verifying that all media appears in the library with metadata and watch status intact.

**Acceptance Scenarios**:

1. **Given** NAS SMB shares are mounted on HOLYGRAIL, **When** Plex scans the library paths, **Then** all previously available movies, TV shows, and other media are detected and playable.
2. **Given** a user had partially watched a TV series on the old Plex instance, **When** they open Plex on HOLYGRAIL, **Then** their watch progress and on-deck items are restored via Plex account sync after the fresh library scan completes.
3. **Given** NAS shares are mounted on HOLYGRAIL, **When** the server reboots, **Then** the NAS mounts reconnect automatically and Plex continues serving media without manual remounting.

---

### User Story 3 - Emby Decision (Priority: P2)

The Camelot admin wants to retire Emby and document the rationale. Running two media servers on the Pi was feasible but redundant, and on HOLYGRAIL Emby would compete for GPU/RAM with Plex and Ollama. Retiring Emby simplifies operations and frees resources for higher-priority workloads.

**Why this priority**: Important for reducing operational complexity, but doesn't block core Plex functionality. The decision should be made during migration rather than deferred.

**Independent Test**: Can be tested by reviewing the documented decision and confirming the chosen option is implemented — either Emby running alongside Plex on HOLYGRAIL, or Emby stopped on the Pi and marked as decommissioned.

**Acceptance Scenarios**:

1. **Given** the admin is evaluating Emby's role, **When** they review the documented decision, **Then** the rationale (keep or retire) is clearly stated with justification.
2. **Given** the decision is to keep Emby, **When** Emby is deployed on HOLYGRAIL, **Then** it runs alongside Plex without resource conflicts and can access the same NAS media shares.
3. **Given** the decision is to retire Emby, **When** the migration is complete, **Then** the Emby container is stopped on the Media Server Pi and infrastructure documentation reflects its decommissioned status.

---

### User Story 4 - Media Server Pi Repurposing (Priority: P3)

After Plex (and optionally Emby) have been migrated off the Media Server Pi (192.168.10.150), the admin wants to either assign the Pi a new role or power it down. The Pi should not continue running services that have moved to HOLYGRAIL. Note: Pi-hole DNS also runs on this Pi and must be accounted for separately.

**Why this priority**: This is a cleanup task that follows the migration. It doesn't block any user-facing functionality but is important for maintaining a clean infrastructure.

**Independent Test**: Can be tested by confirming media server containers are stopped on the Pi, infrastructure documentation is updated, and management scripts reflect the Pi's new status.

**Acceptance Scenarios**:

1. **Given** Plex and Emby have been migrated off the Pi, **When** the admin checks the Pi, **Then** media server containers are stopped and no longer set to auto-start.
2. **Given** the Pi is being repurposed or decommissioned, **When** the admin reviews infrastructure documentation, **Then** the Pi's new role (or decommissioned status) is accurately documented.
3. **Given** Pi-hole DNS runs on this same Pi (192.168.10.150), **When** media services are removed, **Then** Pi-hole continues operating unaffected (it is not part of this migration scope).

---

### Edge Cases

- What happens when the NAS becomes unreachable while Plex is running on HOLYGRAIL? Plex should show libraries as unavailable but recover automatically when NAS connectivity is restored.
- What happens if multiple users are transcoding simultaneously? The RTX 2070 Super's NVENC encoder supports multiple concurrent sessions; Plex should handle this gracefully up to the GPU's session limit.
- What happens to existing Plex client devices (TVs, phones, etc.) that were connected to the Pi instance? The admin's own devices will see the new server automatically via Plex account. During the parallel run, both "Herring" (Pi) and the new HOLYGRAIL server will appear in client device lists.
- What happens to external shared users? A fresh Plex install creates a new server identity — shared users will NOT automatically see the new server. The admin must re-invite all shared users on the HOLYGRAIL instance via Settings > Users & Sharing. During the parallel run, shared users retain access to "Herring" until the Pi is decommissioned.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST run Plex with access to the host GPU for hardware-accelerated transcoding via NVENC.
- **FR-002**: System MUST make Plex accessible via its web interface on the standard port (32400) on the LAN and remotely via Plex account authentication.
- **FR-003**: System MUST automatically restart Plex after a server reboot without manual intervention.
- **FR-004**: System MUST mount NAS SMB shares on HOLYGRAIL so Plex can access all media files (movies, TV shows, music, etc.).
- **FR-005**: NAS mounts MUST persist across server reboots and reconnect automatically.
- **FR-006**: System MUST rebuild Plex libraries via fresh scan of NAS mounts; watch history is restored via Plex account sync (no database migration from Pi).
- **FR-007**: Admin MUST document the Emby retirement decision with rationale in infrastructure documentation.
- **FR-008**: Emby container MUST be stopped on the Media Server Pi and marked as decommissioned.
- **FR-009**: The Pi-based Plex instance MUST remain running during the validation period until the admin confirms HOLYGRAIL Plex is fully functional, at which point Pi media server containers are stopped.
- **FR-010**: Infrastructure documentation and management scripts MUST be updated to reflect the Pi's new status after media services are removed.
- **FR-011**: Pi-hole DNS on the Media Server Pi (192.168.10.150) MUST remain operational and unaffected by the media service migration.
- **FR-012**: Sonarr and Radarr on Torrentbox MUST be reconfigured to connect to the HOLYGRAIL Plex instance so that newly downloaded media triggers library updates on the new server.
- **FR-013**: Admin MUST re-invite all existing shared/external Plex users to the new HOLYGRAIL server instance, since a fresh install creates a new server identity and shares do not carry over from the old "Herring" server.

### Key Entities

- **Media Server (Plex)**: The primary media streaming service, serving content to household devices. Consumes media files from NAS shares and transcodes them on demand using GPU hardware encoding.
- **Media Server (Emby)**: An alternative media streaming service currently running alongside Plex. Subject to a keep/retire decision during this migration.
- **NAS Shares**: SMB network shares hosted on the NAS Pi (192.168.10.105) containing all media files. Must be network-mounted on HOLYGRAIL for Plex/Emby to access.
- **Media Server Pi**: The Raspberry Pi 5 at 192.168.10.150 currently hosting Plex, Emby, and Pi-hole. Will have media services removed; Pi-hole remains.
- **HOLYGRAIL**: The central server (Ryzen 7800X3D / RTX 2070 Super) that will become the new home for Plex and potentially Emby.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Media files that previously required software transcoding on the Pi now transcode using hardware acceleration, with the Plex dashboard confirming "(hw)" next to active transcode sessions.
- **SC-002**: Users can stream media from the new Plex instance within 5 seconds of pressing play, including content that requires transcoding.
- **SC-003**: All media previously available on the Pi-based Plex instance is accessible on the HOLYGRAIL-based instance with no missing libraries.
- **SC-004**: The system recovers fully from a server reboot — Plex is accessible and NAS shares are mounted — without any manual intervention.
- **SC-005**: Pi-hole DNS resolution on 192.168.10.150 continues to function with zero downtime during and after the migration.
- **SC-006**: The Emby keep/retire decision is documented and the chosen path is fully implemented.
- **SC-007**: The Media Server Pi has no running media server containers after migration is complete.
- **SC-008**: All previously shared external users can stream from the new HOLYGRAIL Plex instance with no loss of library access.

## Assumptions

- The NAS Pi (192.168.10.105) is stable and will continue serving SMB shares to HOLYGRAIL; NAS reliability is outside the scope of this migration.
- HOLYGRAIL already has Ubuntu, Docker, and NVIDIA drivers/container toolkit installed (Phase 1 prerequisites completed per F1.1, F1.2, F1.3).
- The user has a Plex Pass subscription (required for hardware transcoding in Plex).
- Libraries will be rebuilt via fresh scan (no Pi database migration); Plex account sync handles watch history restoration.
- Pi-hole DNS migration (if desired) is a separate effort and not part of this feature.
- The admin's own Plex client devices will discover the new server automatically via Plex account; external shared users must be re-invited manually since shares are tied to the server identity (not the account).
- The RTX 2070 Super supports sufficient concurrent NVENC sessions for household usage (typically 3-5 simultaneous streams).
