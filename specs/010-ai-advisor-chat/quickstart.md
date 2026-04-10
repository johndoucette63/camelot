# Quickstart: AI-Powered Advisor Chat

**Feature**: 010-ai-advisor-chat
**Audience**: Single-admin (you), running on HOLYGRAIL with the existing advisor stack
**Purpose**: Final validation after implementation. Walk through each user story and confirm the acceptance criteria match reality. Run this AFTER `/speckit.implement` completes.

---

## Prerequisites

1. Ollama is running on HOLYGRAIL with `llama3.1:8b` loaded (F3.1 done).
   - Verify: `ssh john@holygrail "docker exec ollama ollama list"` shows `llama3.1:8b`.
2. The advisor stack is up to date with this feature's code, including the new migration.
   - Deploy: `ssh john@holygrail "cd ~/camelot/advisor && git pull && docker compose up -d --build"`
   - Verify migration ran: `ssh john@holygrail "docker compose exec advisor-backend alembic current"` shows revision `003`.
3. The advisor backend can reach Ollama.
   - Verify: `ssh john@holygrail "docker compose exec advisor-backend curl -s http://ollama:11434/api/version"` returns a version.
4. The advisor frontend is built and served at `http://advisor.holygrail`.

## Setup: create a test state

To exercise the grounding behaviors you need a known network state:

- At least one device OFFLINE. Easiest: temporarily unplug one of the Pis, or `ssh john@holygrail "docker compose exec advisor-backend python -c 'import asyncio; from app.database import async_session; from sqlalchemy import update; from app.models.device import Device; async def m(): \n  async with async_session() as s: await s.execute(update(Device).where(Device.hostname==\"nas\").values(is_online=False)); await s.commit()\nasyncio.run(m())'"` (or manually through a SQL shell).
- At least one service UNHEALTHY. Easiest: stop a non-critical container on HOLYGRAIL (e.g., a test nginx) and wait one health-check cycle, or manually insert a row into `health_check_results`.

Record what you set up so you can verify the advisor's answers.

---

## US-1 validation: Ask and get a conversational reply (P1)

1. Open `http://advisor.holygrail` in a browser.
2. Click the chat entry in the sidebar / navigate to `/chat`.
3. **Expect** (fresh state, no prior conversations in the DB): an empty chat thread and a message input. ✅ AC1.
   - If you are re-running this quickstart after prior runs, you will instead see the most recent prior conversation resumed (✅ AC1a). To force the fresh-state path, truncate the chat tables first: `ssh john@holygrail "docker compose exec advisor-db psql -U advisor advisor -c 'TRUNCATE conversations CASCADE'"`.
4. Type `Hello, who are you?` and press Enter.
5. **Expect**:
   - Your message appears in the thread immediately, visually distinct (aligned one side, different background). ✅ AC2.
   - Within 3 seconds, the first words of the advisor's reply appear and stream progressively token by token. ✅ AC3 + SC-001.
6. Type two more short questions and submit each.
7. Scroll up in the thread and confirm all messages are visible in chronological order. ✅ AC4.
8. On HOLYGRAIL, temporarily stop Ollama: `ssh john@holygrail "docker stop ollama"`.
9. Submit another message in the chat.
10. **Expect**: within 5 seconds you see a clear, user-friendly failure message in the thread (not a raw error or infinite spinner). ✅ AC5 + SC-005.
11. Restart Ollama: `ssh john@holygrail "docker start ollama"`. Wait ~5 seconds for readiness.
12. Click **New chat**. Submit a message. Confirm normal streaming resumes.

---

## US-2 validation: Answers are grounded in live network state (P2)

1. Click **New chat**.
2. Ask: `What devices are on my network?`
3. **Expect**: the response enumerates real devices by hostname/IP from the inventory (HOLYGRAIL, Torrentbox, NAS, Pi-hole DNS, Mac Workstation or whatever is currently in the DB). It must NOT invent device names. ✅ AC1.
4. Ask: `Which services are down right now?`
5. **Expect**: the response names the service you marked unhealthy during setup, and does not list healthy services as down. ✅ AC2.
6. Ask: `What's been going on with alerts recently?`
7. **Expect**: the response references actual recent alert entries (if any) rather than hypothetical ones. If there are no recent alerts, the advisor should say so explicitly. ✅ AC3.
8. Ask: `What's the uptime of my refrigerator compressor?`
9. **Expect**: the advisor acknowledges it doesn't have that data rather than inventing an answer. ✅ AC4 + SC-004.

---

## US-3 validation: Representative question set (P3)

Click **New chat** between each question (or keep them in one thread — either is fine, but separate threads give you clean reads). Ask each question in turn and compare the answer to your known ground truth.

1. **Q1**: `What devices are on my network?`
   - Expect: enumerates real devices by hostname/IP. No hallucinated entries.
2. **Q2**: `Which services are down right now?`
   - Expect: names the service(s) you marked unhealthy. No healthy services listed.
3. **Q3**: `Is the Torrentbox VPN working?`
   - Expect: references the actual current VPN health-check state for the torrent container. If unknown, admits so.
4. **Q4**: `Summarize what's going on with alerts right now.`
   - Expect: summarizes actual recent alerts from the database. If none, says so.

**Pass bar (SC-002)**: all 4 responses reference real devices/services/events, and zero responses confidently invent nonexistent entities.

---

## Cancellation validation (FR-005a)

1. Click **New chat**.
2. Ask a question likely to produce a long reply: `Give me a detailed summary of everything you know about my network.`
3. While the advisor is streaming, click the **Stop** button.
4. **Expect**:
   - The stream stops immediately (no more tokens arrive).
   - The partial reply produced up to that point remains visible in the thread (not cleared).
   - A visible indicator shows the message was cancelled (e.g., greyed-out, "(stopped)" label — whatever the UI uses).
5. Reload the page.
6. **Expect**: the conversation is still there, the cancelled message is still there with its partial content, and `cancelled=TRUE` in the database:
   ```bash
   ssh john@holygrail "docker compose exec advisor-db psql -U advisor advisor -c \"SELECT id, role, cancelled, length(content) FROM messages ORDER BY created_at DESC LIMIT 5\""
   ```

---

## Persistence & resume validation (FR-006, FR-006a)

1. With a non-empty conversation visible in the chat, refresh the browser tab (`Cmd+R` / `Ctrl+R`).
2. **Expect**: the same conversation, with the same messages, is displayed. ✅ FR-006a.
3. On HOLYGRAIL, restart the backend: `ssh john@holygrail "cd ~/camelot/advisor && docker compose restart advisor-backend"`.
4. Wait ~5 seconds, then refresh the tab again.
5. **Expect**: the conversation is still there (it lives in Postgres, not process memory). ✅ FR-006 "backend restart" clause.
6. Click **New chat**.
7. **Expect**: a fresh empty thread appears. The prior conversation is no longer displayed but is still in the database:
   ```bash
   ssh john@holygrail "docker compose exec advisor-db psql -U advisor advisor -c \"SELECT id, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 5\""
   ```
   (You should see at least two rows.)
8. Refresh the tab.
9. **Expect**: the freshly-created empty conversation is the active one (most recent `updated_at`), or — if no messages have been added yet — the previously active one. Either is acceptable per FR-006a wording; just confirm no UI error.

---

## Multi-turn memory validation (FR-010a)

1. Click **New chat**.
2. Ask: `Which services are down right now?`
3. Once the reply completes, ask a follow-up that relies on prior context: `Tell me more about the first one you mentioned.`
4. **Expect**: the advisor references the specific service it named in its previous reply, not a generic one. If it says "which one?" or "I haven't mentioned any services", multi-turn memory is broken.

---

## Observability sanity checks

1. Tail the advisor backend logs during a chat:
   ```bash
   ssh john@holygrail "cd ~/camelot/advisor && docker compose logs -f advisor-backend | grep chat"
   ```
2. **Expect**: one structured JSON log line per submitted question, including conversation id, message id, duration, token count (from Ollama's `eval_count`), and — if applicable — cancellation or error details.

---

## Constitution alignment check

- [ ] No external network calls during chat (all traffic stays on `192.168.10.0/24`). Verify by temporarily blocking outbound internet on HOLYGRAIL (`sudo ufw deny out to any from any`) and confirming the chat still works, then re-enable.
- [ ] Health endpoint still returns 200: `curl http://advisor.holygrail/health`.
- [ ] No new containers were added to `advisor/docker-compose.yml`.

---

## If any step fails

- **Streaming never starts**: Check Ollama reachability from inside the backend container (`docker compose exec advisor-backend curl http://ollama:11434/api/version`), and confirm `OLLAMA_BASE_URL` and `OLLAMA_MODEL` env vars are set.
- **Grounding is generic** ("typical home networks have..."): Confirm the prompt assembler is actually reading from the DB — add a log line or inspect the structured logs for the assembled prompt size. Likely the DB session is scoped wrong or the F4.2/F4.3 tables are empty.
- **Partial content not persisted on cancel**: Confirm the `finished_at` / `cancelled` update on disconnect is not swallowed by exception handling. Look for `is_disconnected` handling in `routers/chat.py`.
- **"Most recent conversation" on reload shows the wrong one**: Confirm `updated_at` is being bumped on message insert (trigger? app-level update? either works, but it has to happen).
