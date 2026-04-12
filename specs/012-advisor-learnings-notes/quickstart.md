# Quickstart: Advisor Learnings & Curated Notes

**Branch**: `012-advisor-learnings-notes` | **Date**: 2026-04-12

## Prerequisites

- Docker + Docker Compose running on HOLYGRAIL
- Advisor app deployed (FastAPI backend + React frontend + PostgreSQL)
- Ollama running at `ollama.holygrail` with `llama3.1:8b` model (needed for US-4 suggestions only)

## Verify the Feature

### 1. Run the migration

```bash
# On HOLYGRAIL (or via deploy script)
cd /opt/advisor
docker compose exec backend alembic upgrade head
```

Confirm migration 005 applied:
```bash
docker compose exec backend alembic current
# Should show: 005_advisor_notes (head)
```

### 2. Verify seed data

Open the app in a browser and navigate to the **Playbook** page (new nav entry).

**Expected**: Three seed entries visible:
- "NAS RAID Scrub Schedule" (pinned, tags: maintenance, nas)
- "VPN Credential Rotation" (tags: maintenance, security, vpn)
- "DNS Ownership" (tags: dns, convention)

### 3. Create a device note (US-1)

1. Navigate to **Devices** page
2. Click on the NAS device row to open the detail modal
3. In the notes section, click "Add note"
4. Enter: `Test note — NAS has 4TB RAID-5 array, replaced drive 2 on 2026-03-01`
5. Click Save

**Expected**: Note appears in the device's notes list, sorted most recent first.

### 4. Verify advisor grounding (US-1 + US-4 integration)

1. Navigate to **Chat**
2. Start a new conversation
3. Ask: `What do you know about the NAS?`

**Expected**: The advisor's response references the note you just created AND the seed playbook entry about the RAID scrub schedule. It should attribute the sources (e.g., "According to your note on the NAS...").

### 5. Create and filter playbook entries (US-2)

1. Navigate to **Playbook**
2. Click "New entry"
3. Title: `Test Maintenance Window`
4. Body: `Saturday 1 AM–5 AM is the weekly maintenance window`
5. Tags: type `maintenance` (should autocomplete from seed data)
6. Save

**Expected**: Entry appears in the list. Click the `maintenance` tag filter — should show this entry plus the two seed entries tagged `maintenance`.

### 6. Create a service note (US-3)

1. Navigate to **Services**
2. Click on the Plex service row
3. In the notes tab (alongside health history), click "Add note"
4. Enter: `Upgraded to v1.40 on 2026-03-15. GPU transcoding working after driver fix.`
5. Save

**Expected**: Note appears in the service's notes list.

### 7. Test pinned notes budget behavior (FR-012)

1. Navigate to the NAS device and pin the test note from step 3
2. Navigate to **Chat** and start a fresh conversation
3. Ask: `Give me an overview of all my notes`

**Expected**: The advisor references both the pinned device note and the pinned seed playbook entry. Unpinned notes may or may not appear depending on context budget.

### 8. Test LLM-suggested notes (US-4)

1. Navigate to **Chat**
2. Have a conversation mentioning facts: `The Torrentbox VPN is currently using Mullvad. We switched from PIA last month because of the speed issues.`
3. Click the **"Suggest notes"** button

**Expected**: A review panel appears with 1–2 suggestions (e.g., a note about Mullvad VPN on the Torrentbox). Approve one to verify it creates a real note. Reject one to verify it doesn't reappear.

### 9. Test graceful degradation (FR-013, FR-019)

```bash
# Temporarily stop Ollama
ssh john@holygrail "docker stop ollama"
```

1. Navigate to **Chat** and start a conversation
2. The chat should still work (Ollama being down affects chat itself, but notes loading should degrade independently)
3. If Ollama is up but notes DB query fails, the advisor should still respond (just without the Notes section)

```bash
# Restart Ollama
ssh john@holygrail "docker start ollama"
```

### 10. Test cascade delete (FR-021)

1. If you have a test device with notes, delete the device
2. Verify the device's notes are also deleted (check Playbook page or use API: `GET /api/notes?target_type=device&target_id={id}` should return empty)

## Cleanup

If testing in a development environment, you can remove test data:
```bash
# Delete all non-seed notes via psql
docker compose exec db psql -U advisor -d advisor -c "DELETE FROM notes WHERE id > 3;"
```
