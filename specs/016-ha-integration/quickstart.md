# Quickstart — Home Assistant Integration

**Feature**: 016-ha-integration
**Purpose**: End-to-end validation of the integration after implementation. Run this from the Mac workstation with the advisor deployed on HOLYGRAIL and the Home Assistant Pi operational.

The quickstart is the authoritative acceptance check for this feature. Each step maps to one or more spec acceptance scenarios and success criteria (SC numbers noted inline).

---

## Prerequisites

- Advisor is deployed on HOLYGRAIL (`bash scripts/deploy-advisor.sh` completed) with migration `008_home_assistant_integration.py` applied.
- `ADVISOR_ENCRYPTION_KEY` is set in `advisor/.env` on HOLYGRAIL (32-byte URL-safe base64 — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). The advisor container has been restarted since it was set.
- Home Assistant is running on its dedicated Pi (IP and hostname recorded in `docs/INFRASTRUCTURE.md`).
- You have created a Home Assistant long-lived access token: HA UI → user profile → **Long-Lived Access Tokens** → **Create Token**. Copy the token (it is only shown once).
- The Home Assistant companion app on your phone is registered with HA as a notify service (you can see its service name under **Developer Tools → Services** filtered to `notify`).

---

## 0. Baseline documentation update (Assumptions, docs/INFRASTRUCTURE.md)

Record the current HA deployment in `docs/INFRASTRUCTURE.md`:
- Home Assistant host IP and hostname.
- Home Assistant core version.
- Integrations in use (HomeKit, Aqara, Thread, MQTT, others).
- Identified Thread border routers with their physical location and role.
- Any known Thread fragmentation or pairing issues.

Commit the doc update on the `016-ha-integration` branch.

---

## 1. Configure the HA connection (SC-001, Story 1 AC-1, AC-2)

1. Open the advisor UI → **Settings → Home Assistant**.
2. Enter the HA base URL (e.g., `http://homeassistant.local:8123` or the Pi's IP).
3. Paste the long-lived access token.
4. Click **Test Connection**. Expected: green "OK — connected" pill within 5 seconds.
5. Click **Save**.

**Verify**:
- The Home Assistant tab in the main nav lights up.
- Open **Home Assistant** in the nav: within 60 seconds the entity snapshot table populates with entities from the curated domains.
- Each entity shows friendly name, domain, state, and last-changed timestamp.

**Negative test** — intentionally enter a wrong token, click **Test Connection**. Expected: explicit "Authentication failed" message (not a generic "failed"). Correct the token, re-save.

---

## 2. Entity state reflects HA changes (Story 1 AC-3)

1. In HA, toggle a test switch or simulate a binary_sensor state change (e.g., open/close a monitored door).
2. Wait up to one poll cycle (60 s default).
3. Refresh the advisor's Home Assistant tab (or let the auto-refresh fire).

**Verify**: the toggled entity's `state` and `last_changed` match HA.

---

## 3. Thread topology (SC-002, Story 2 AC-1–AC-3, AC-5)

1. Open **Home Assistant → Thread** in the advisor.
2. Compare the border router list to HA's **Settings → Devices & Services → Thread → Network configuration**.

**Verify**: each border router appears with name, model, online state, and attached device count matching HA.

**Negative test — border router offline** (SC-002):
1. Power-cycle one HomePod or Aqara hub (border router).
2. Wait one poll cycle.

**Verify**:
- The advisor Thread view marks that border router **offline** within 60 seconds.
- A recommendation appears in the recommendations panel naming the failed border router.
- Any orphaned devices show `parent_border_router_id` as `null` or fall back to `last_seen_parent_id`.

Power the border router back on. Within one poll, its status returns to online and the recommendation auto-resolves.

**Empty-state test** (Story 2 AC-5): if your HA instance has no Thread integration at all, the Thread view renders a clear "No Thread data found" panel rather than a blank page or error.

---

## 4. Device inventory merge (SC-008)

1. Open **Devices** in the advisor.

**Verify**:
- Every HomePod / Aqara hub / other HA device with LAN presence shows up as **one** row — no duplicates. The "HA" column shows the connectivity type (`lan_wifi`, `lan_ethernet`).
- Thread-only devices (e.g., battery-powered Aqara sensors) appear as rows with `mac_address = null`, `ip_address = null`, and `ha_connectivity_type = thread`.
- For a device that both the LAN scanner saw (has MAC/IP) and HA reports, the row carries both provenance markers (scanner + HA).

**Sanity check**: pick a Thread device, rename it in HA, wait one poll cycle. Its `friendly_name` updates in the advisor. Its `ha_device_id` does not change (stability check, clarification Q1).

---

## 5. Notification forwarding (SC-003, Story 3 AC-1, AC-5)

1. Open **Settings → Notification Sinks**.
2. Click **Add sink** → type **Home Assistant**.
3. The "Service" dropdown populates from the live HA `notify.*` list. Pick `mobile_app_<your device>`.
4. Leave `min_severity` at **critical** (default).
5. Save.

**Trigger a critical alert** — easiest path:
- Stop the advisor's Plex health check target on HOLYGRAIL (`docker stop plex`) to force a `service_down` alert. Wait up to 5 minutes for the sustained-breach window.

**Verify**:
- Within 30 seconds of the alert becoming active, the HA companion app on your phone shows a push notification with the alert title, message, severity, and target.
- In the advisor's alert history, the alert row shows `delivery_status = sent`, `delivery_attempt_count = 1`, `delivery_last_attempt_at` populated.

Restart Plex (`docker start plex`); the alert resolves and no further notifications fire.

**Negative test — HA unreachable mid-delivery** (Story 3 AC-4):
1. Stop Home Assistant (`docker stop homeassistant` on the HA Pi) or block the advisor→HA LAN path temporarily.
2. Trigger a critical alert by the same method as above.

**Verify**:
- The alert record shows `delivery_status` cycling through `failed → failed → failed → terminal` over roughly 5 minutes (attempts at approximately 0 s, 30 s, 60 s, 120 s, 240 s).
- On reaching `terminal`, a recommendation appears: "Critical alert not delivered to Home Assistant after 4 attempts."
- No retry loop continues after the 5-minute budget.

Restart Home Assistant. Subsequent new alerts deliver normally.

**Mute respect** (Story 3 AC-5):
1. Mute the `(rule_id, target_id)` pair using the existing mute mechanism from 011-recommendations-alerts.
2. Re-trigger the alert.

**Verify**: the alert is recorded with `delivery_status = suppressed` and **no** push notification fires.

---

## 6. Failure-mode behavior (SC-004, SC-005, FR-023, FR-024)

**HA unreachable** (SC-004):
1. Stop Home Assistant or unplug its Ethernet.
2. Wait two poll cycles.

**Verify**:
- The advisor's Home Assistant tab shows the prior snapshot with a visible "stale" marker and the staleness timestamp.
- A **warning** recommendation: "Home Assistant is unreachable." The advisor's own dashboards (Devices, Services, Alerts) continue to render normally.

Restart HA. Within one poll cycle the status flips back to `ok` and the stale marker clears. Polling resumes without operator intervention.

**Token rotation** (SC-005):
1. In HA, revoke the long-lived access token (user profile → Long-Lived Access Tokens → trash icon).
2. Wait up to one poll cycle.

**Verify**:
- The Home Assistant tab shows `status = auth_failure`.
- A **critical** recommendation: "Home Assistant authentication failed — rotate token in Settings."

Create a new long-lived token in HA, paste it into the advisor's Settings page, save. Next poll cycle → `status = ok`, recommendation auto-resolves.

---

## 7. AI chat grounding (SC-006, Story 2 AC-4)

1. Open the advisor's **Chat** page.
2. Ask: "Which of my Thread border routers have the most devices attached?"

**Verify**: the answer names the current border routers from HA with attached-device counts consistent with the Thread view. The advisor did not ask you to paste anything — the context was pulled automatically.

3. Ask a non-IoT question (e.g., "What's the status of Plex?"). The response should **not** include irrelevant HA entity data, confirming the classifier-driven grounding (research R9).

---

## 8. Regression check — inventory, alerts, chat

Before closing the task, re-run the quickstarts for the features this one extends:

- 008-network-discovery-inventory: the device scanner still populates scanner-discovered rows with `ha_device_id = null`.
- 011-recommendations-alerts: existing rules still fire; existing `webhook`-type sinks (if any) still deliver; mutes/cool-downs unchanged.
- 010-ai-advisor-chat: non-HA chat questions behave as before.

---

## 9. Update `docs/INFRASTRUCTURE.md`

Add a "Home Assistant Integration" subsection documenting:
- HA base URL the advisor uses.
- Env var requirement (`ADVISOR_ENCRYPTION_KEY`).
- How to rotate the HA token (HA UI + advisor Settings).
- How to decommission (DELETE /settings/home-assistant or the UI "Remove" button).

Commit the doc update.

---

## Exit criteria

- All "Verify" bullets above pass.
- No regressions in the referenced prior-feature quickstarts.
- `docs/INFRASTRUCTURE.md` is updated.
- The feature branch is ready to merge.
