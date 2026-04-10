# Feature Specification: AI-Powered Advisor Chat

**Feature Branch**: `010-ai-advisor-chat`
**Created**: 2026-04-10
**Status**: Draft
**Input**: User description: "AI-Powered Advisor Chat — Conversational interface backed by a local LLM, grounded in live network state (device inventory, service health, alerts)."

## Clarifications

### Session 2026-04-10

- Q: Which grounding data sources are in scope for v1, given that several of the 8 originally proposed representative questions depend on data (time-series metrics, log aggregation, IoT/Thread topology, per-host resource stats) that the advisor does not yet have plumbed? → A: v1 grounds only on F4.2 device inventory and F4.3 service registry / health / alerts. Representative question set reduced to the 4 questions answerable from those sources (inventory, services down, VPN status, alert summary). The other 4 original questions (capacity planning, Thread topology, latency time-series, log anomalies) are explicitly deferred to future features that add those data sources.
- Q: How should conversation history be persisted, and what is the "session" boundary in FR-006? → A: Persist conversations and messages server-side in the advisor's Postgres via a new Alembic migration adding `conversations` and `messages` tables. History survives page reloads and backend restarts. The UI shows only the currently active conversation in v1 — no past-session browser or list of historical conversations. Cross-session browsing remains deferred.
- Q: Should the admin be able to cancel an in-flight advisor response? → A: Yes. An explicit stop control MUST be visible while the advisor is replying. Activating it cancels the model generation on the backend and saves whatever partial text was produced as the final content of that advisor message, so the admin can still see what was being said at the moment of cancellation.
- Q: Should the advisor have multi-turn conversational memory, and how should prior turns be included in each model call? → A: Yes, full multi-turn memory. Every model call MUST include all prior user and advisor messages in the current conversation plus a freshly-assembled network context snapshot for the new question. No per-turn windowing or summarization in v1; the existing FR-012 fallback (summarize or prioritize if the assembled context would exceed the model's usable context window) remains the safety net.
- Q: On page load, does the advisor resume the most recent conversation or start fresh, and is there a "New chat" control? → A: On page load, the advisor MUST fetch and display the most recent conversation so a quick reload preserves context. The chat UI MUST expose a visible "New chat" control that starts a fresh conversation on demand; the prior conversation remains persisted in the database but is no longer the active one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask the advisor a question and get a conversational reply (Priority: P1)

The admin opens the advisor dashboard, navigates to the chat, types a question in plain English (e.g., "What services are running on my network?"), and receives a conversational reply from the advisor. The exchange is visible as a scrollable thread with clear separation between user messages and advisor responses.

**Why this priority**: This is the core interaction of the feature. Without a working chat loop — input, response, visible history — no other capability in this feature delivers any value. It must exist before grounding, validation, or persistence matter.

**Independent Test**: Launch the advisor, open the chat, send a message, and confirm a response appears in the thread. The chat can be tested as a "generic assistant" even before network context is wired in — you should see a natural-language reply and see it remain in the visible history as you continue the conversation.

**Acceptance Scenarios**:

1. **Given** the admin is on the advisor dashboard and no prior conversations exist, **When** they open the chat panel, **Then** an empty conversation thread and a message input are visible.
1a. **Given** the admin is on the advisor dashboard and a prior conversation exists, **When** they open the chat panel, **Then** the most recent conversation is resumed and displayed with its full message history, and the message input is visible.
2. **Given** the chat is open, **When** the admin types a question and submits it, **Then** their message appears in the thread and a response from the advisor is rendered in the same thread, visually distinguished from the user's message.
3. **Given** a response is being generated, **When** the advisor begins producing output, **Then** the reply streams into the thread progressively rather than appearing only after completion.
4. **Given** several messages have been exchanged, **When** the admin scrolls the thread, **Then** the full message history for the current session is preserved and readable in chronological order.
5. **Given** the local language model backend is unreachable, **When** the admin submits a question, **Then** the advisor displays a clear, non-technical failure message instead of hanging or showing a raw error.

---

### User Story 2 - Advisor answers are grounded in the current network state (Priority: P2)

When the admin asks a question that depends on the state of their home network — which devices are online, which services are healthy, what alerts are active — the advisor responds with answers that reference the actual devices, services, and events present on the network at that moment, not generic knowledge.

**Why this priority**: Ungrounded chat is just a local chatbot. Grounding is what makes this an *advisor*. It is the primary differentiator of the feature, but it depends on US-1 being in place first because there must be a working chat loop to ground into.

**Independent Test**: With at least one device offline and at least one service unhealthy, ask the advisor "What's wrong with my network right now?" and confirm the response names the actual offline device(s) and unhealthy service(s) by name — not hypothetical examples.

**Acceptance Scenarios**:

1. **Given** the network has a known set of devices and services in known states, **When** the admin asks "What devices are on my network?", **Then** the response lists the actual devices currently in inventory, referencing them by their real names or addresses.
2. **Given** one or more services are currently in an unhealthy state, **When** the admin asks "Which services are down right now?", **Then** the response identifies those specific services by name and does not list healthy services as down.
3. **Given** recent alerts exist in the system, **When** the admin asks "What's been going on with alerts recently?", **Then** the response summarizes the actual recent alerts rather than describing hypothetical ones.
4. **Given** the admin asks a question whose answer cannot be determined from available network state, **When** the advisor responds, **Then** it acknowledges the limitation rather than fabricating a confident-sounding answer.
5. **Given** the current network state is very large, **When** a question is asked, **Then** the advisor still responds successfully without exceeding the model's context limits or producing a truncation error visible to the user.

---

### User Story 3 - Advisor handles the representative question set accurately (Priority: P3)

The admin can ask any of a known set of representative questions about the network — covering device inventory, service health, VPN status, and recent alerts — and receive a useful, grounded, non-hallucinated answer for each.

**Why this priority**: This is the quality bar that determines whether the feature is actually useful in practice. It builds on US-1 (chat works) and US-2 (grounding works) and validates that both come together to produce trustworthy answers. It is not strictly required to ship a minimal version but is required before the feature can be called "done".

**Independent Test**: Run each of the representative questions below through the advisor in sequence and confirm each answer (a) references the correct real-world entities, (b) does not invent nonexistent devices or services, and (c) admits uncertainty when the underlying data is unavailable.

**Acceptance Scenarios**:

1. **Given** the advisor is connected to live network state, **When** the admin asks "What devices are on my network?", **Then** the response enumerates real devices from inventory.
2. **Given** at least one service is unhealthy, **When** the admin asks "Which services are down right now?", **Then** the response identifies those services by name.
3. **Given** the torrent VPN is being monitored, **When** the admin asks "Is the Torrentbox VPN working?", **Then** the response reflects the actual current VPN status as reported by the service registry.
4. **Given** alert history is available from the service registry, **When** the admin asks "Summarize what's going on with alerts right now", **Then** the response summarizes actual recent alert entries.

**Deferred questions**: The following question categories were part of the original F4.4 proposal but are explicitly deferred to future features that add the required data sources to the advisor:

- Capacity planning / workload migration advice (requires per-host resource stats not yet plumbed into the advisor).
- IoT / Thread network topology questions (requires Home Assistant integration — Phase 6, blocked).
- Time-series questions like "NAS latency spiked at 2am — is that normal?" (requires InfluxDB/Smokeping queries to be exposed to the advisor backend).
- Log anomaly questions like "Anything unusual in the logs in the last 24 hours?" (requires log aggregation to be plumbed into the advisor).

---

### Edge Cases

- **Local language model backend unreachable**: The admin sees a clear, user-friendly message and can retry without reloading the dashboard.
- **Model response extremely slow or stalled**: Streaming output makes progress visible; the admin can press the stop control at any time to cancel generation, and the partial text already produced is saved as the final content of that advisor message.
- **Empty or whitespace-only input**: The message is not submitted and no advisor response is triggered.
- **Network state temporarily unavailable** (inventory or service health data cannot be loaded): The advisor still responds but clearly indicates that its answer is not grounded in current state.
- **Very large network context**: The context assembled for grounding is summarized or trimmed to fit within the model's usable context window, without silently dropping critical state.
- **Question that names a device or service that does not exist**: The advisor explicitly says the named entity is not present in inventory rather than inventing plausible details about it.
- **Rapid successive messages**: Messages are processed in order and each reply is attributed to the correct prompt in the thread.
- **Admin leaves and returns to the chat during the session**: The thread of messages exchanged so far is still visible; starting a new session produces a fresh thread.

## Requirements *(mandatory)*

### Functional Requirements

#### Chat interface

- **FR-001**: The advisor dashboard MUST provide a chat interface accessible from the main navigation (either as a dedicated page or as a persistent panel).
- **FR-002**: The chat interface MUST display conversation history as a scrollable thread in chronological order.
- **FR-003**: User messages and advisor responses MUST be visually distinguished from each other in the thread.
- **FR-004**: The user MUST be able to compose and submit a message via a text input.
- **FR-005**: Advisor responses MUST stream into the thread progressively as they are generated, not only appear once complete.
- **FR-005a**: While an advisor response is being generated, the chat MUST expose a visible stop control that cancels the in-flight response. On cancellation, the backend MUST cancel the underlying model generation and MUST save any text already produced as the final content of that advisor message, so the partial reply remains visible in the thread.
- **FR-006**: Conversation history MUST be persisted server-side so that the active conversation survives both a browser page reload and a backend process restart. In v1, the UI MUST show only the currently active conversation; a browser of past conversations is not required.
- **FR-006a**: On page load, the chat UI MUST fetch and display the most recent conversation (if one exists) so that a quick reload preserves context. If no conversations exist yet, the chat MUST start a new empty conversation.
- **FR-006b**: The chat UI MUST expose a visible "New chat" control that starts a fresh conversation on demand. Activating it makes the new conversation the active one; the prior conversation MUST remain persisted in the database but is no longer displayed.

#### Language model backend integration

- **FR-007**: User questions MUST be answered by a locally hosted language model; no question or response content may leave the home network.
- **FR-008**: The language model used to generate responses MUST be configurable, with a sensible default selected for the project's hardware.
- **FR-009**: When the local language model backend is unreachable or errors, the chat MUST display a clear, user-friendly failure message and allow the admin to retry.

#### Network grounding

- **FR-010**: At the time a question is submitted, the advisor MUST assemble a fresh context summary describing the current state of the network from the v1 grounding sources: the device inventory (F4.2) and the service registry, service health, and alerts (F4.3). The context MUST include at minimum: the set of known devices with online/offline state, the set of tracked services with health state, and a summary of alerts from the last 24 hours. The context MUST be re-assembled on every turn (not cached across turns) so follow-up questions reflect the latest network state. Additional data sources (time-series metrics, logs, IoT topology, per-host resource stats) are out of scope for v1.
- **FR-010a**: Every model call MUST include the full prior exchange (all earlier user and advisor messages) in the current conversation in addition to the freshly-assembled network context for the new question, so that follow-up questions can reference prior turns conversationally.
- **FR-011**: The assembled context MUST reference devices and services by their real identifiers (name, address, or equivalent) so that responses can cite them directly.
- **FR-012**: The context assembled for each question MUST be sized to fit within the model's usable context window; when the full state would exceed that limit, the system MUST summarize or prioritize rather than silently truncate critical information.
- **FR-013**: When grounding data for a question cannot be retrieved (e.g., inventory or health service is unavailable), the advisor MUST still respond and MUST indicate that the response is not grounded in current state.

#### Answer quality

- **FR-014**: When the advisor does not have sufficient grounding data to answer confidently, it MUST acknowledge uncertainty rather than fabricate specifics.
- **FR-015**: The advisor MUST be validated against the representative question set defined in US-3 before the feature is considered complete. Each question must receive a response that references real entities when applicable and does not invent nonexistent devices, services, or events.

### Key Entities

- **Conversation**: A persisted, ordered sequence of messages exchanged in a single chat session. Stored server-side with a stable identifier, a creation timestamp, and (optionally) a last-activity timestamp. Retrieving a conversation by its identifier returns its full message history.
- **Message**: A persisted entry in a conversation, identified as either a user message or an advisor message, with text content and a timestamp. Advisor messages may be produced in streaming fragments and MUST be finalized (saved in their complete form) once the model has finished generating them.
- **Network Context Snapshot**: A point-in-time summary of the network assembled when a question is asked, combining device inventory state, service health state, and recent alert activity into a form the language model can reference by name.
- **Language Model Backend**: The locally hosted inference service that produces advisor replies. Identified by a configurable model selection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From the moment the admin submits a question, the first words of the advisor's reply appear in the chat within 3 seconds under normal conditions.
- **SC-002**: For the 4 representative questions defined in US-3, the advisor produces answers that reference real devices, services, or events from the current network state in all 4 cases, with zero answers that confidently invent nonexistent entities.
- **SC-003**: 100% of question content and response content remains on the home network (no external calls for inference).
- **SC-004**: When the advisor lacks the data to answer a question, it acknowledges uncertainty rather than fabricating specifics in 100% of observed cases during validation.
- **SC-005**: When the language model backend is unreachable, the admin sees a clear failure message within 5 seconds rather than an indefinite hang or a raw error.
- **SC-006**: The admin can submit a follow-up question without reloading or losing the visible history of the current session.

## Assumptions

- A locally hosted language model backend is already deployed on the central server and reachable from the advisor application. (Phase 3 / F3.1 dependency.)
- A device inventory is already maintained and queryable, providing current devices and their online/offline state. (F4.2 dependency.)
- A service registry with current health state is already maintained and queryable. (F4.3 dependency.)
- Recent alert data is available from the monitoring stack and queryable by the advisor backend.
- A single trusted admin user is the sole user of the chat; multi-user permissioning, per-user history isolation, and audit logging are out of scope for this feature.
- Conversations and messages are persisted server-side in the advisor's existing Postgres database. A browser of historical conversations in the UI is out of scope for v1 — only the active conversation is shown — but the data is stored such that a future feature can add that browser without a data migration.
- Voice input, file uploads, and image attachments are out of scope for this feature.
- The advisor is read-only with respect to the network — it answers questions but does not take remediation actions (restart services, reboot devices, edit configurations). Action-taking is a future feature.
- The default model selected is appropriate for the central server's hardware; model tuning and fine-tuning are out of scope.
- The representative question set in US-3 is treated as the acceptance bar for answer quality; broader open-ended question quality is not measured for this feature.
