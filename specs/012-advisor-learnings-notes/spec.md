# Feature Specification: Advisor Learnings & Curated Notes

**Feature Branch**: `012-advisor-learnings-notes`  
**Created**: 2026-04-12  
**Status**: Draft  
**Input**: User description: "Advisor Learnings & Curated Notes — user-curated notes/playbook layer that feeds the advisor chat's grounding context, with optional LLM-assisted suggestions"

## Clarifications

### Session 2026-04-12

- Q: How are note suggestions triggered — automatic on chat close, manual button, or both? → A: Manual only — a "Suggest notes" button the admin clicks when they want suggestions.
- Q: Are playbook tags free-form text or selected from a predefined set? → A: Free-form text input with autocomplete suggestions from previously used tags.
- Q: Should the advisor attribute which note it's drawing from in its responses? → A: Yes — the advisor should cite the source note or playbook entry when referencing curated knowledge.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record and Reference Device Notes (Priority: P1)

The admin notices that a device has a recurring quirk — for example, the NAS goes offline every Sunday at 2 AM for a RAID scrub. Today, the admin has to re-explain this context to the advisor every time they start a new chat. With this feature, the admin navigates to the Devices page, opens the device detail, and adds a note: "Goes offline Sunday 2 AM–3 AM for RAID scrub — not a real outage." From that point on, whenever the admin asks the advisor "Why is the NAS offline Sunday morning?", the advisor already knows the answer because the note is included in its grounding context.

**Why this priority**: This is the core value proposition — turning the advisor from a stateless tool into one that accumulates durable, trusted context about the network. Per-device notes are the most natural starting point because the device inventory already exists and device-specific quirks are the most common type of knowledge the admin wants to persist.

**Independent Test**: Can be fully tested by creating a device note, starting a fresh chat session, and verifying the advisor references the note content without being told about it.

**Acceptance Scenarios**:

1. **Given** a device exists in the inventory, **When** the admin opens the device detail and adds a new note with a Markdown body, **Then** the note is saved and appears in the device's notes list sorted by most recent first.
2. **Given** a device has one or more notes, **When** the admin starts a new advisor chat and asks a question about that device, **Then** the advisor's response reflects knowledge from the device's notes and attributes the source (e.g., "According to your note on [device]...").
3. **Given** a device has a pinned note, **When** the advisor assembles its grounding context, **Then** the pinned note is always included regardless of context budget pressure.
4. **Given** the admin creates a note and restarts the application, **When** they return to the device detail, **Then** the note is still present and visible.
5. **Given** an existing note, **When** the admin edits or deletes it, **Then** the changes are reflected immediately in the device detail view and in subsequent advisor chat sessions.

---

### User Story 2 - Cross-Cutting Playbook Entries (Priority: P2)

The admin wants to record network-wide knowledge that isn't tied to any specific device or service — things like "VPN credentials rotate on the first Monday of every month", "DNS is managed by Cloudflare, login is in 1Password", or "Maintenance window is Saturday 1 AM–5 AM." The admin navigates to a dedicated Playbook page, creates entries with titles and optional tags (e.g., `maintenance`, `vendor`, `security`), and can filter by tag to find entries quickly. The advisor references these playbook entries when answering general network questions.

**Why this priority**: Cross-cutting knowledge (schedules, conventions, contacts, vendor details) is the second most valuable type of context for the advisor. It provides foundational "site runbook" knowledge that improves every conversation, not just device-specific ones. It also delivers standalone value — even without per-device or per-service notes, a playbook page is useful.

**Independent Test**: Can be fully tested by creating playbook entries with different tags, filtering by tag in the UI, and verifying the advisor references playbook content when asked relevant questions.

**Acceptance Scenarios**:

1. **Given** the admin navigates to the Playbook page, **When** they create a new entry with a title, Markdown body, and one or more tags, **Then** the entry is saved and appears in the playbook list.
2. **Given** multiple playbook entries exist with different tags, **When** the admin filters by a specific tag (e.g., `maintenance`), **Then** only entries with that tag are shown.
3. **Given** playbook entries exist, **When** the admin asks the advisor a general network question (e.g., "When is the maintenance window?"), **Then** the advisor's response references the relevant playbook entry.
4. **Given** a playbook entry is pinned, **When** the advisor assembles its grounding context, **Then** the pinned entry is always included.
5. **Given** a playbook entry exists, **When** the admin edits its title, body, or tags, **Then** the changes are persisted and reflected in subsequent advisor sessions.

---

### User Story 3 - Record and Reference Service Notes (Priority: P3)

The admin wants to document context about specific services — for example, "Plex was upgraded to v1.40 on 2026-03-15, rolled back GPU transcoding due to driver conflict" or "Sonarr is configured to prefer 1080p HEVC, do not change without checking disk space on NAS." The admin opens the Services page, clicks a service, and adds notes alongside the existing health history view. The advisor references these notes when asked about the service.

**Why this priority**: Extends the per-device notes pattern to services. Slightly lower priority because service-specific context is less frequently needed than device quirks or network-wide playbook entries, but it completes the coverage of the two main entity types in the system.

**Independent Test**: Can be fully tested by creating a service note, starting a fresh chat, and verifying the advisor references the note when asked about that service.

**Acceptance Scenarios**:

1. **Given** a service exists in the service registry, **When** the admin opens the service detail and adds a note, **Then** the note is saved and appears in the service's notes list.
2. **Given** a service has notes, **When** the admin asks the advisor about that service, **Then** the advisor's response reflects knowledge from the service's notes.
3. **Given** the admin creates a service note, **When** they navigate away and return to the service detail, **Then** the note persists.

---

### User Story 4 - LLM-Suggested Notes with Approval (Priority: P4)

After a productive advisor chat where the admin mentioned several useful facts ("the NAS scrub happens Sunday nights", "we switched DNS providers last week"), the admin clicks a "Suggest notes" button to ask the advisor to propose durable notes from the conversation. The suggestions appear in a review panel showing the proposed note body and which entity it would attach to. The admin can approve each suggestion as-is, edit it before saving, or reject it. Nothing is saved without explicit approval. Rejected suggestions are remembered so the same suggestion doesn't resurface in future conversations.

**Why this priority**: This is an enhancement layer on top of the core notes system. It makes note-taking more convenient but is not essential — the admin can always create notes manually. It also requires the core notes infrastructure (US-1, US-2, US-3) to be in place first.

**Independent Test**: Can be fully tested by having a chat conversation that mentions network facts, triggering note suggestions, and verifying the approve/edit/reject workflow persists or dismisses suggestions correctly.

**Acceptance Scenarios**:

1. **Given** the admin has had a conversation mentioning network facts, **When** they click the "Suggest notes" button, **Then** the system presents 0–3 suggested notes with proposed targets (device, service, or playbook) and body text.
2. **Given** a suggestion is presented, **When** the admin approves it, **Then** the note is saved to the appropriate notes collection and is visible in the corresponding detail view.
3. **Given** a suggestion is presented, **When** the admin chooses to edit it, **Then** an editor opens pre-filled with the suggestion, and the admin can modify it before saving.
4. **Given** a suggestion is presented, **When** the admin rejects it, **Then** the suggestion is dismissed and not shown again in future conversations.
5. **Given** no noteworthy facts were discussed, **When** the admin clicks the "Suggest notes" button, **Then** the system returns zero suggestions rather than inventing low-value entries.

---

### User Story 5 - Notes Survive Backup and Restore (Priority: P5)

The admin's curated notes represent significant accumulated domain knowledge. Notes must be included in the standard database backup path so that restoring from a backup recovers all notes. No separate backup step should be required.

**Why this priority**: This is a data durability requirement. It's low priority because it's largely a natural consequence of storing notes in the same database as everything else, but it must be explicitly verified.

**Independent Test**: Can be fully tested by creating notes, performing a database backup, restoring from that backup to a fresh instance, and verifying all notes are present.

**Acceptance Scenarios**:

1. **Given** the admin has created device notes, service notes, and playbook entries, **When** the database is backed up and restored to a fresh deployment, **Then** all notes are present and visible.
2. **Given** a fresh deployment restored from a backup, **When** the admin starts a new advisor chat, **Then** the advisor's grounding context includes all restored notes.

---

### Edge Cases

- What happens when the admin creates a note with an empty body? The system should reject it and display a validation message.
- What happens when the admin tries to add a note to a device or service that has been deleted? The system should prevent orphaned notes — notes should be removed when their parent entity is deleted.
- What happens when the total size of all pinned notes exceeds the advisor's context budget? The system should enforce a maximum number of pinned notes per category (e.g., 20) and warn the admin when approaching the limit.
- What happens when the notes data source is temporarily unavailable while assembling the advisor prompt? The advisor should degrade gracefully — omit the notes section and continue with the rest of the prompt, following the existing graceful degradation pattern.
- What happens when the admin pins a large number of notes across devices, services, and playbook? Unpinned notes should be the first content trimmed from the advisor context when budget pressure occurs, before conversation history.
- What happens when the LLM suggestion call fails or times out? The system should silently skip suggestions — manual note creation still works. No error should block the user.
- What happens when the admin creates a note with the maximum allowed body length? The system should enforce a size limit per note (2 KB) and reject notes exceeding it with a clear message.

## Requirements *(mandatory)*

### Functional Requirements

#### Notes Management (Core)

- **FR-001**: System MUST allow the admin to create, read, update, and delete free-form notes attached to individual devices.
- **FR-002**: System MUST allow the admin to create, read, update, and delete free-form notes attached to individual services.
- **FR-003**: System MUST provide a dedicated Playbook page where the admin can create, read, update, and delete cross-cutting notes not tied to a specific device or service.
- **FR-004**: Each note MUST support a Markdown text body with a maximum size of 2 KB.
- **FR-005**: Each note MUST have a "pinned" flag that the admin can toggle. Pinned notes receive priority inclusion in the advisor's grounding context.
- **FR-006**: Each note MUST track creation and last-updated timestamps.
- **FR-007**: Playbook entries MUST support a title field and one or more optional free-form tags for categorization (e.g., `maintenance`, `vendor`, `convention`, `security`). The tag input MUST offer autocomplete suggestions drawn from previously used tags.
- **FR-008**: The Playbook page MUST support filtering entries by tag.
- **FR-009**: Notes MUST be displayed sorted by most recent first in all list views.
- **FR-010**: The system MUST enforce a maximum of 20 pinned notes per category (per-device, per-service, and playbook) and warn the admin when the limit is reached.

#### Advisor Chat Integration

- **FR-011**: The advisor chat MUST include an "Admin Notes" section in its grounding context that contains all pinned per-device notes, per-service notes, and playbook entries. Each note in the context MUST be labeled with its source (e.g., device name, service name, or "Playbook") so the advisor can attribute it in responses.
- **FR-012**: Unpinned notes MUST be included in the advisor context only when total prompt size is under the character budget. When budget pressure occurs, unpinned notes MUST be trimmed before conversation history.
- **FR-013**: If the notes data source is unavailable during prompt assembly, the system MUST degrade gracefully — omit the notes section and assemble the rest of the prompt normally.
- **FR-028**: When the advisor references knowledge from a curated note in its response, it MUST attribute the source (e.g., "According to your note on the NAS..." or "Per your playbook entry on VPN rotation...").

#### LLM-Suggested Notes

- **FR-014**: The system MUST provide a "Suggest notes" button in the chat interface that, when clicked, generates 0–3 note suggestions based on the conversation content. Suggestions are never generated automatically.
- **FR-015**: Each suggestion MUST include a proposed target (device, service, or playbook), a target identifier (if device or service), and a proposed note body.
- **FR-016**: Suggestions MUST be presented in a review panel where the admin can approve (save as-is), edit (modify before saving), or reject (dismiss permanently) each suggestion.
- **FR-017**: No suggested note MUST be persisted without an explicit approval action from the admin.
- **FR-018**: Rejected suggestions MUST be remembered so the same suggestion is not shown again in future conversations.
- **FR-019**: If the LLM suggestion service is unavailable, the system MUST skip suggestion generation silently. Manual note creation MUST remain fully functional.

#### Data Integrity

- **FR-020**: Notes MUST persist across application restarts.
- **FR-021**: Notes MUST be deleted when their parent entity (device or service) is deleted — no orphaned notes.
- **FR-022**: Notes MUST be included in the standard database backup path with no separate backup step required.
- **FR-023**: The system MUST validate that note bodies are not empty and do not exceed the 2 KB size limit.

#### Navigation & UI

- **FR-024**: Per-device notes MUST be accessible from the device detail view on the Devices page.
- **FR-025**: Per-service notes MUST be accessible from the service detail view on the Services page, alongside the existing health history.
- **FR-026**: The Playbook page MUST have its own entry in the main navigation.
- **FR-027**: The application MUST include at least 3 example seed playbook entries on initial deployment (e.g., NAS scrub schedule, VPN rotation schedule, DNS ownership note).

### Key Entities

- **Note**: A user-authored piece of Markdown text attached to a device, service, or standing alone as a playbook entry. Key attributes: body, pinned status, creation time, last-updated time. For playbook entries, also includes a title and tags.
- **Playbook Entry**: A cross-cutting note with a title and tag-based categorization, not tied to any specific device or service. Lives on its own dedicated page.
- **Note Suggestion**: A system-proposed note generated from conversation content. Key attributes: proposed target type, target identifier, proposed body, approval status. Exists only in the review workflow until approved (becomes a Note) or rejected (recorded to prevent re-suggestion).
- **Rejected Suggestion**: A record of a dismissed suggestion, identified by content hash, used to prevent the same suggestion from resurfacing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Admin can create a device note and see it referenced by the advisor in a fresh chat session within 30 seconds of saving.
- **SC-002**: Admin can create, tag, and filter playbook entries, completing the full create-and-find-by-tag workflow in under 1 minute.
- **SC-003**: When asked about a topic covered by a pinned note, the advisor references the note content in its response at least 90% of the time.
- **SC-004**: Advisor chat continues to function normally (responds within expected timeframe) when the notes data source is temporarily unavailable — no user-facing errors.
- **SC-005**: After a conversation mentioning 2+ network facts, the suggestion mechanism proposes at least 1 relevant note (when suggestions are triggered).
- **SC-006**: All notes (device, service, and playbook) survive a full database backup-and-restore cycle with zero data loss.
- **SC-007**: The advisor's response time does not degrade by more than 10% when 50 pinned notes are included in the grounding context compared to zero notes.

## Assumptions

- Single-admin deployment — no multi-user permissions or author tracking required.
- The existing device inventory and service registry are in place and stable (dependencies on the discovery and service registry features).
- The advisor chat is operational with its current prompt assembly mechanism, and adding a new section to the grounding context is a supported extension point.
- The LLM service (used for note suggestions) may be unavailable — all core note functionality works without it.
- Notes are plain Markdown text only — no images, file attachments, or embedded rich content.
- Full-text search across notes is out of scope for this version; tag-based filtering on the Playbook page is sufficient for the expected volume (~50 entries or fewer).
- Version history and undo for note edits are out of scope — edits overwrite the previous content.
- Notes stay local to this deployment instance — no cloud sync or cross-instance sharing.
