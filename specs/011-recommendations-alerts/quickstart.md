# Quickstart: Recommendations & Alerts

**Feature**: 011-recommendations-alerts
**Purpose**: End-to-end validation of the shipped feature. Run after `/speckit.implement` completes. These steps exercise every user story's primary flow against the deployed advisor stack on HOLYGRAIL.

**Assumptions**:

- The advisor backend + frontend are deployed to HOLYGRAIL via `bash scripts/deploy-advisor.sh` (per memory: never `git pull` on HOLYGRAIL).
- Migration `004_recommendations_alerts.py` has been applied.
- Ollama is running at `http://holygrail:11434` with `llama3.1:8b` pulled.
- The device inventory (F4.2) has at least `torrentbox`, `nas`, `mediaserver` scanned.
- The service registry (F4.3) has at least one service that can be toggled (e.g. Plex or Deluge).
- A Home Assistant instance on the LAN is reachable (optional for Step 5).

---

## 0. Deploy and smoke-test

```bash
# From the Mac workstation
bash scripts/deploy-advisor.sh

# Backend health
curl -s http://advisor.holygrail/api/health | jq .
# Expect: {"status":"ok"}

# Engine started? Tail the backend logs for the first cycle
ssh john@holygrail "docker logs advisor-backend 2>&1 | grep rule_engine.cycle.completed | tail -n 1"
# Expect: JSON line with rules_evaluated ≥ 5
```

If no `rule_engine.cycle.completed` line appears within 90 seconds, stop and check `docker logs advisor-backend` for a startup error.

---

## 1. Validate User Story 1 — Proactive rule-based recommendations (P1)

### 1a. CPU rule fires within one sustained window

```bash
# Drive torrentbox CPU to >80% for at least 5 minutes
ssh torrentbox "yes > /dev/null &"  # start CPU burner

# Wait 5–6 minutes, then check the recommendations endpoint
sleep 360
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "pi_cpu_high")'
```

**Expected**: one entry with `rule_id: "pi_cpu_high"`, `target_label: "torrentbox"`, `severity: "warning"`, and a message mentioning migration to HOLYGRAIL.

```bash
# Stop the burner
ssh torrentbox "pkill yes"

# Wait one engine cycle (60 s) and confirm auto-resolve
sleep 90
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "pi_cpu_high")'
```

**Expected**: empty. The alert should now appear in the history log as `resolved` with `resolution_source: "auto"`.

### 1b. Disk rule fires

```bash
# Create a large sparse file on torrentbox to push disk usage past threshold
ssh torrentbox "fallocate -l 2G /tmp/disk_test_fill.bin"
# If this isn't enough to cross 85% on your system, adjust size or use /var/log

sleep 90
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "disk_high")'

# Cleanup
ssh torrentbox "rm /tmp/disk_test_fill.bin"
```

**Expected**: at least one `disk_high` entry appears while the file is in place; auto-resolves within two cycles after cleanup.

### 1c. Service-down rule fires

```bash
# Stop a tracked service temporarily (pick one you own and can restart quickly)
ssh john@holygrail "docker stop plex"

# Wait 6 minutes (5-minute threshold + cycle)
sleep 360
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "service_down")'

# Bring it back up
ssh john@holygrail "docker start plex"

sleep 90
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "service_down")'
```

**Expected**: critical alert while Plex is down, auto-resolves after restart.

### 1d. Ollama unavailable rule fires

```bash
# Stop Ollama temporarily
ssh john@holygrail "docker stop ollama"

sleep 90
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "ollama_unavailable")'

# Also confirm the panel response still returns successfully (graceful degradation)
curl -s -o /dev/null -w "%{http_code}\n" http://advisor.holygrail/api/recommendations
# Expect: 200

# Restart Ollama
ssh john@holygrail "docker start ollama"
```

**Expected**: info-severity `ollama_unavailable` alert while Ollama is down, and `ai_narrative` is absent from the response during the outage (FR-020 graceful degradation).

### 1e. Device-offline rule fires (FR-006)

```bash
# Pick a Pi that's safe to power down briefly (not HOLYGRAIL).
# Stop metric reporting by shutting down the Pi OR blocking return traffic at the firewall.
ssh nas "sudo shutdown -h +1"  # graceful shutdown with 1-minute warning

# Wait for the device_offline_minutes threshold (default 10 min) + one cycle.
sleep 720
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "device_offline")'
```

**Expected**: one entry with `rule_id: "device_offline"`, `target_label: "nas"`, `severity: "warning"`. No `pi_cpu_high` or `disk_high` alerts should appear for the offline device (FR-006: distinguish missing data from bad metric).

```bash
# Power the Pi back up and wait for metrics to resume
# (physical power cycle or scripted WoL)
sleep 180
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "device_offline")'
```

**Expected**: empty. Auto-resolved once metrics start flowing again.

### 1f. Dedup (FR-004)

```bash
# Re-run 1a to trigger CPU alert again while it's still active. Confirm no duplicate row.
curl -s "http://advisor.holygrail/api/alerts?rule_id=pi_cpu_high&state=active" | jq '.total'
# Expect: at most 1 active alert for a given (rule, target). No duplicates from cycle-to-cycle.
```

---

## 2. Validate User Story 2 — Configurable thresholds

```bash
# Read current thresholds
curl -s http://advisor.holygrail/api/settings/thresholds | jq '.thresholds[] | select(.key == "cpu_percent")'
# Expect: value 80, default 80, unit "%"

# Lower the threshold to force a CPU alert at current (low) load
curl -s -X PUT http://advisor.holygrail/api/settings/thresholds/cpu_percent \
  -H 'Content-Type: application/json' \
  -d '{"value": 5}'

sleep 420  # wait 5 min sustained + one cycle
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "pi_cpu_high")'
# Expect: alert fires against every Pi above 5% CPU (essentially all of them)

# Restore default
curl -s -X PUT http://advisor.holygrail/api/settings/thresholds/cpu_percent \
  -H 'Content-Type: application/json' \
  -d '{"value": 80}'

sleep 90
# Validation error path
curl -s -X PUT http://advisor.holygrail/api/settings/thresholds/cpu_percent \
  -H 'Content-Type: application/json' \
  -d '{"value": 999}'
# Expect: 400 with "value must be between 10 and 100"
```

---

## 3. Validate User Story 3 — Alert history log

```bash
# List recent alerts
curl -s "http://advisor.holygrail/api/alerts?limit=20" | jq '.items | length, .total'

# Filter by severity
curl -s "http://advisor.holygrail/api/alerts?severity=warning&limit=50" | jq '.items[] | .severity' | sort -u
# Expect: only "warning"

# Filter by device
DEVICE_ID=$(curl -s http://advisor.holygrail/api/devices | jq '.[] | select(.hostname == "torrentbox") | .id')
curl -s "http://advisor.holygrail/api/alerts?device_id=$DEVICE_ID&limit=50" | jq '.items[] | .target_label' | sort -u

# Acknowledge an active alert
ALERT_ID=$(curl -s http://advisor.holygrail/api/recommendations | jq '.active[0].id')
curl -s -X POST http://advisor.holygrail/api/alerts/$ALERT_ID/acknowledge | jq .
# Expect: state "acknowledged", acknowledged_at set

# Manually resolve
curl -s -X POST http://advisor.holygrail/api/alerts/$ALERT_ID/resolve | jq .
# Expect: state "resolved", resolution_source "manual"
```

Open the dashboard in a browser at `http://advisor.holygrail/alerts` — confirm the table renders with severity/device/date filters and ack/resolve buttons.

---

## 4. Validate Mute (Q4 clarification)

```bash
# Create a 1-hour mute for pi_cpu_high on torrentbox
curl -s -X POST http://advisor.holygrail/api/settings/mutes \
  -H 'Content-Type: application/json' \
  -d "{
    \"rule_id\": \"pi_cpu_high\",
    \"target_type\": \"device\",
    \"target_id\": $DEVICE_ID,
    \"duration_seconds\": 3600,
    \"note\": \"quickstart validation\"
  }" | jq .

# Confirm it's listed
curl -s http://advisor.holygrail/api/settings/mutes | jq '.mutes[] | select(.rule_id == "pi_cpu_high")'

# Trigger the CPU condition again (repeat 1a with shorter threshold)
curl -s -X PUT http://advisor.holygrail/api/settings/thresholds/cpu_percent \
  -H 'Content-Type: application/json' \
  -d '{"value": 5}'
sleep 420

# Verify: no active alert, but the log has suppressed rows
curl -s http://advisor.holygrail/api/recommendations | jq '.active[] | select(.rule_id == "pi_cpu_high" and .target_label == "torrentbox")'
# Expect: empty

curl -s "http://advisor.holygrail/api/alerts?rule_id=pi_cpu_high&include_suppressed=true&limit=5" | jq '.items[] | {state, suppressed}'
# Expect: at least one row with suppressed=true

# Cancel the mute early
MUTE_ID=$(curl -s http://advisor.holygrail/api/settings/mutes | jq '.mutes[0].id')
curl -s -X DELETE http://advisor.holygrail/api/settings/mutes/$MUTE_ID -w "%{http_code}\n"
# Expect: 204

# Restore threshold
curl -s -X PUT http://advisor.holygrail/api/settings/thresholds/cpu_percent \
  -H 'Content-Type: application/json' \
  -d '{"value": 80}'
```

---

## 5. Validate User Story 5 — Home Assistant forwarding (optional)

Skip this section if you do not use Home Assistant.

```bash
# Configure a sink (replace URL with your real HA webhook)
curl -s -X POST http://advisor.holygrail/api/settings/notifications \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "home_assistant",
    "name": "HA on HOLYGRAIL",
    "enabled": true,
    "endpoint": "http://homeassistant.holygrail/api/webhook/camelot-advisor-XXXX",
    "min_severity": "critical"
  }' | jq .

# Run the test delivery
SINK_ID=$(curl -s http://advisor.holygrail/api/settings/notifications | jq '.sinks[0].id')
curl -s -X POST http://advisor.holygrail/api/settings/notifications/$SINK_ID/test | jq .
# Expect: {"ok": true, "status_code": 200, "latency_ms": <number>}

# Verify the endpoint is masked on readback
curl -s http://advisor.holygrail/api/settings/notifications | jq '.sinks[0].endpoint_masked'
# Expect: endpoint with the token portion replaced by "***"

# Trigger a critical alert (service-down is critical)
ssh john@holygrail "docker stop plex"
sleep 360
# Check your HA notifications — a Camelot alert should appear with the alert message + device + timestamp.
ssh john@holygrail "docker start plex"

# Verify local recording is independent of HA delivery (FR-026):
# Disable HA on the router side (block the webhook temporarily), trigger the rule,
# confirm the alert still appears in /alerts and backend logs show ha.delivery_failed.
```

---

## 6. Validate User Story 4 — AI narrative (optional)

```bash
# Trigger two correlated alerts simultaneously (CPU + disk on torrentbox)
ssh torrentbox "yes > /dev/null &"
ssh torrentbox "fallocate -l 2G /tmp/disk_test_fill.bin"

sleep 420

curl -s http://advisor.holygrail/api/recommendations | jq '.ai_narrative'
# Expect: a non-null object with a "text" field that mentions both CPU and disk,
# and plausibly references a correlating activity (imports, scans, etc.).
# Must not invent alerts — only reference the rule-based entries in .active

# Clean up
ssh torrentbox "pkill yes; rm /tmp/disk_test_fill.bin"

# Stop Ollama and re-query to confirm graceful degradation
ssh john@holygrail "docker stop ollama"
curl -s http://advisor.holygrail/api/recommendations | jq '.ai_narrative'
# Expect: null, and the .active list is still returned normally
ssh john@holygrail "docker start ollama"
```

---

## 7. Validate chat context integration (FR-028)

```bash
# Trigger at least one active alert (re-run 1a briefly)
# Then query the chat endpoint and ask about current alerts
curl -s -X POST http://advisor.holygrail/api/chat/conversations \
  -H 'Content-Type: application/json' \
  -d '{"title": "quickstart alert check"}' | jq '.id'
# Capture the conversation id from above and send a message:
CONV=<conversation-id-from-above>
curl -s -N -X POST http://advisor.holygrail/api/chat/conversations/$CONV/messages \
  -H 'Content-Type: application/json' \
  -d '{"content": "What alerts are currently firing?"}'
# Expect: streamed response that references the active alerts from /recommendations
```

---

## 8. Validate retention pruning (spot check)

Cannot be validated in real time (would require waiting 30 days). Instead, confirm the pruning query is wired in by inspecting the backend logs for one cycle:

```bash
ssh john@holygrail "docker logs advisor-backend 2>&1 | grep 'rule_engine.cycle.completed' | tail -n 5"
```

Look for `alerts_pruned` as a field in the JSON; value will typically be 0 on a fresh deploy. The field's presence confirms the code path exists.

---

## 9. Clean up any lingering test state

```bash
# Ensure no burners or test files are left on torrentbox
ssh torrentbox "pkill yes 2>/dev/null; rm -f /tmp/disk_test_fill.bin"

# Confirm every test alert has auto-resolved
curl -s http://advisor.holygrail/api/recommendations | jq '.active | length'
# Expect: 0 (or only real, unrelated alerts)
```

---

## Acceptance summary

If every section above completes without a failing `# Expect:` check, the feature satisfies User Stories 1–5, all 28 functional requirements, and the nine measurable success criteria from the spec. Report completion in the conversation after the last step.
