"""Prompt assembly — builds the grounded system prompt for the advisor chat.

Pulls live state from the F4.2 device inventory and F4.3 service registry /
health / alerts and formats it as Markdown sections in a single system
message, then appends the full prior exchange in the current conversation
plus the new user question.

Each data source is loaded in its own try/except so a failure in one section
degrades that section to a "could not load" placeholder without breaking the
whole response (FR-013).
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import Alert
from app.models.annotation import Annotation
from app.models.conversation import Conversation
from app.models.device import Device
from app.models.event import Event
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.health_check_result import HealthCheckResult
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.note import Note
from app.models.service_definition import ServiceDefinition
from app.models.thread_border_router import ThreadBorderRouter
from app.models.thread_device import ThreadDevice

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 60_000

# Standalone pronouns and demonstrative phrases that typically refer back
# to an entity mentioned in the prior assistant turn. Matched case-
# insensitively with word boundaries so substrings like "is" in "this" or
# "it" in "item" don't trigger. Order matters — multi-word phrases come
# first so they match before their single-word constituents.
_PRONOUN_PATTERN = re.compile(
    r"\b(?:"
    r"that device|that service|that host|that one|"
    r"the first one|the second one|the last one|"
    r"the same one|the same|"
    r"those|these|them|"
    r"that|this|"
    r"it|its|itself"
    r")\b",
    re.IGNORECASE,
)

_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Classifier tokens for IoT / home-automation / Thread questions. When a
# token matches, we include the Home Assistant grounding section (feature
# 016 / research R9). Classifier-driven inclusion prevents prompt pollution
# on unrelated questions.
_IOT_KEYWORDS = (
    "thread",
    "border router",
    "zigbee",
    "home assistant",
    "homeassistant",
    "aqara",
    "homekit",
    "homepod",
    "matter",
    "iot",
    "smart home",
    "smart plug",
    "smart light",
    "smart bulb",
    "smart switch",
    "motion sensor",
    "door sensor",
    "leak sensor",
)


def _query_is_iot_related(query: str) -> bool:
    """Classify whether the user's question touches the HA / IoT surface.

    Case-insensitive substring match — cheap and good enough. False positives
    are fine (they just include extra context); false negatives mean the
    chat can't answer IoT questions, which is worse.
    """
    q = query.lower()
    return any(kw in q for kw in _IOT_KEYWORDS)

# Don't try to resolve referents in long user queries — they usually have
# enough context on their own and the rewrite adds noise.
_REFERENT_MAX_QUERY_CHARS = 200

SYSTEM_PREAMBLE = """You are the Camelot network advisor, a conversational assistant for a single home administrator managing a small home network.

Answer questions about the user's network using the live state provided below. Always reference real devices and services by their actual names and IP addresses. If the answer cannot be determined from the state below, say so clearly — do not invent devices, services, or facts.

Formatting rules:
- When listing multiple devices, services, alerts, or events, use a Markdown bullet list — one item per line, each starting with `- `.
- For short single-value answers, reply in one sentence without a list.
- Use `**bold**` sparingly to highlight device or service names when that aids scanning.
- Use `inline code` for IP addresses, ports, and technical identifiers (e.g., `192.168.10.129`, `:32400`).
- Keep responses tight. Prefer a list of 5 facts over a paragraph of 5 sentences.

Follow-up questions and pronoun resolution:
- When the user uses a pronoun like "it", "that", "those", "that device", "that service", "the first one", "the same one", always resolve it to the most recently mentioned specific entity (device, service, or IP address) from the immediately prior assistant turn.
- Never default to HOLYGRAIL or any other device unless the user explicitly names it or it was the actual referent in the prior turn.
- If the referent is genuinely ambiguous, ask the user which entity they mean rather than guessing.

Admin notes:
- The "Admin Notes" section below contains durable notes written by the administrator about their network. Treat these as authoritative facts.
- When your answer draws on an admin note, cite where it came from (e.g., "According to your note on the NAS…" or "Per your playbook entry on VPN rotation…")."""


async def _load_devices_section(db: AsyncSession) -> str:
    result = await db.execute(
        select(Device).options(selectinload(Device.annotation)).order_by(Device.ip_address)
    )
    devices = result.scalars().all()
    if not devices:
        return "## Devices\n(no devices in inventory)"

    total = len(devices)
    online = sum(1 for d in devices if d.is_online)
    lines = [f"## Devices ({online}/{total} online)"]
    for d in devices:
        name = d.hostname or d.mac_address
        role = d.annotation.role if d.annotation else "unknown"
        desc = d.annotation.description if d.annotation else None
        tags = d.annotation.tags if d.annotation else []
        state = "ONLINE" if d.is_online else "OFFLINE"
        parts = [f"- {name} ({d.ip_address}) — role={role} — {state}"]
        if tags:
            parts.append(f"tags={tags}")
        if desc:
            parts.append(f"note={desc}")
        lines.append(" — ".join(parts))
    return "\n".join(lines)


async def _load_services_section(db: AsyncSession) -> str:
    # Load enabled service definitions along with the single latest health
    # check result per service. We use a correlated subquery for the latest
    # check rather than pulling full history.
    result = await db.execute(
        select(ServiceDefinition).where(ServiceDefinition.enabled.is_(True))
    )
    services = result.scalars().all()
    if not services:
        return "## Services\n(no services registered)"

    # Fetch all recent health check results in one go and index by service_id.
    hcr_result = await db.execute(
        select(HealthCheckResult).order_by(HealthCheckResult.checked_at.desc())
    )
    all_checks = hcr_result.scalars().all()
    latest_by_service: dict[int, HealthCheckResult] = {}
    for hc in all_checks:
        if hc.service_id not in latest_by_service:
            latest_by_service[hc.service_id] = hc

    healthy = sum(
        1
        for s in services
        if latest_by_service.get(s.id) and latest_by_service[s.id].status == "up"
    )
    lines = [f"## Services ({healthy}/{len(services)} healthy)"]
    for s in services:
        latest = latest_by_service.get(s.id)
        if latest is None:
            status_label = "UNCHECKED"
            extra = ""
        else:
            status_label = latest.status.upper()
            parts: list[str] = [
                f"last_checked={latest.checked_at.isoformat()}Z"
            ]
            if latest.response_time_ms is not None:
                parts.append(f"rtt={latest.response_time_ms}ms")
            if latest.error:
                parts.append(f"error={latest.error[:120]}")
            extra = " — " + " ".join(parts)
        lines.append(
            f"- {s.name} on {s.host_label} ({s.host}:{s.port}) — {status_label}{extra}"
        )
    return "\n".join(lines)


ACTIVE_ALERTS_LIMIT = 20


async def _load_alerts_section(db: AsyncSession) -> str:
    """Render the currently-open rule-based alerts for chat grounding (FR-028).

    Returns a Markdown `## Active Alerts` section listing up to
    ``ACTIVE_ALERTS_LIMIT`` alerts ordered critical → warning → info, then
    by ``created_at DESC``. If more exist beyond the limit, a trailing
    `(N more not shown)` line is appended so the model knows the list was
    capped.
    """
    severity_rank = case(
        (Alert.severity == "critical", 0),
        (Alert.severity == "warning", 1),
        (Alert.severity == "info", 2),
        else_=3,
    )

    base_where = [
        Alert.state.in_(("active", "acknowledged")),
        Alert.suppressed.is_(False),
    ]

    total = (
        await db.execute(select(func.count()).select_from(Alert).where(*base_where))
    ).scalar_one()

    if total == 0:
        return "## Active Alerts\n(no active alerts)"

    result = await db.execute(
        select(Alert)
        .options(selectinload(Alert.device), selectinload(Alert.service))
        .where(*base_where)
        .order_by(severity_rank, Alert.created_at.desc())
        .limit(ACTIVE_ALERTS_LIMIT)
    )
    alerts = result.scalars().all()

    lines = [f"## Active Alerts ({total} open)"]
    for a in alerts:
        ts = a.created_at.isoformat() + "Z"
        target = ""
        if a.device is not None:
            target = f" — device={a.device.hostname or a.device.ip_address}"
        if a.service is not None:
            target += f" — service={a.service.name}"
        state_tag = f" [{a.state}]" if a.state == "acknowledged" else ""
        lines.append(
            f"- {ts} — {a.severity.upper()}{target} — {a.message}{state_tag}"
        )

    if total > ACTIVE_ALERTS_LIMIT:
        lines.append(f"({total - ACTIVE_ALERTS_LIMIT} more not shown)")

    return "\n".join(lines)


async def _load_events_section(db: AsyncSession) -> str:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.device))
        .where(Event.timestamp >= cutoff)
        .order_by(Event.timestamp.desc())
        .limit(50)
    )
    events = result.scalars().all()
    if not events:
        return "## Recent events (last 24h)\n(no events in the last 24 hours)"

    lines = [f"## Recent events (last 24h, {len(events)} shown)"]
    for e in events:
        ts = e.timestamp.isoformat() + "Z"
        device_label = ""
        if e.device is not None:
            device_label = f" — {e.device.hostname or e.device.ip_address}"
        lines.append(f"- {ts} — {e.event_type}{device_label}")
    return "\n".join(lines)


async def _load_notes_section(db: AsyncSession) -> str:
    """Render the admin notes section for chat grounding.

    Pinned notes are always included. Unpinned notes are included only if
    they fit within a secondary character budget so they don't push the
    prompt over the limit. Notes are grouped by target for attribution.
    """
    # Load all notes — pinned first, then unpinned by updated_at desc.
    result = await db.execute(
        select(Note).order_by(Note.pinned.desc(), Note.updated_at.desc())
    )
    all_notes = result.scalars().all()
    if not all_notes:
        return "## Admin Notes\n(no admin notes)"

    # Resolve device/service labels for attribution headers.
    device_ids = {n.target_id for n in all_notes if n.target_type == "device" and n.target_id}
    service_ids = {n.target_id for n in all_notes if n.target_type == "service" and n.target_id}

    device_labels: dict[int, str] = {}
    if device_ids:
        rows = await db.execute(
            select(Device)
            .options(selectinload(Device.annotation))
            .where(Device.id.in_(device_ids))
        )
        for d in rows.scalars().all():
            label = d.hostname or d.mac_address
            device_labels[d.id] = f"{label} ({d.ip_address})"

    service_labels: dict[int, str] = {}
    if service_ids:
        rows = await db.execute(
            select(ServiceDefinition).where(ServiceDefinition.id.in_(service_ids))
        )
        for s in rows.scalars().all():
            service_labels[s.id] = f"{s.name} on {s.host_label}"

    # Budget for unpinned notes: allow up to 8000 chars for the whole
    # notes section so it doesn't dominate the prompt.
    NOTES_BUDGET = 8_000
    chars_used = 0

    lines = ["## Admin Notes"]
    for note in all_notes:
        # Build the attribution header + body line.
        pin_tag = "[pinned] " if note.pinned else ""
        if note.target_type == "device":
            header = f"Device: {device_labels.get(note.target_id or 0, f'id={note.target_id}')}"
        elif note.target_type == "service":
            header = f"Service: {service_labels.get(note.target_id or 0, f'id={note.target_id}')}"
        else:
            header = f"Playbook: {note.title or '(untitled)'}"

        entry = f"### {header}\n- {pin_tag}{note.body}"

        if note.pinned:
            lines.append(entry)
            chars_used += len(entry)
        else:
            if chars_used + len(entry) <= NOTES_BUDGET:
                lines.append(entry)
                chars_used += len(entry)
            # else: silently skip — unpinned notes trimmed under budget

    return "\n\n".join(lines)


async def _load_home_assistant_section(db: AsyncSession) -> str:
    """Grounding block for the Home Assistant integration (feature 016).

    Compact on purpose — a rich HA install can have thousands of entities
    and the whole snapshot would blow the prompt budget without helping the
    answer. We show:
      * connection health (last-success age, current error class)
      * counts: total entities, Thread border routers online/total, Thread
        devices online/total
      * up to 20 most-recently-changed entities with entity_id, friendly
        name, state, last_changed
    """
    conn_row = (await db.execute(select(HomeAssistantConnection).where(HomeAssistantConnection.id == 1))).scalar_one_or_none()
    if conn_row is None or conn_row.base_url is None:
        return "## Home Assistant\n(no Home Assistant connection configured)"

    lines: list[str] = ["## Home Assistant"]
    if conn_row.last_error:
        lines.append(f"- status: DEGRADED ({conn_row.last_error})")
    else:
        lines.append("- status: OK")
    if conn_row.last_success_at:
        age = datetime.utcnow().replace(tzinfo=conn_row.last_success_at.tzinfo) - conn_row.last_success_at
        lines.append(f"- last successful poll: {int(age.total_seconds())}s ago")

    entity_count = (await db.execute(select(func.count()).select_from(HAEntitySnapshot))).scalar_one()
    br_total = (await db.execute(select(func.count()).select_from(ThreadBorderRouter))).scalar_one()
    br_online = (
        await db.execute(
            select(func.count()).select_from(ThreadBorderRouter).where(ThreadBorderRouter.online.is_(True))
        )
    ).scalar_one()
    td_total = (await db.execute(select(func.count()).select_from(ThreadDevice))).scalar_one()
    td_online = (
        await db.execute(
            select(func.count()).select_from(ThreadDevice).where(ThreadDevice.online.is_(True))
        )
    ).scalar_one()
    lines.append(f"- entities tracked: {entity_count}")
    lines.append(f"- Thread border routers: {br_online}/{br_total} online")
    lines.append(f"- Thread devices: {td_online}/{td_total} online")

    recent = (
        await db.execute(
            select(HAEntitySnapshot).order_by(HAEntitySnapshot.last_changed.desc()).limit(20)
        )
    ).scalars().all()
    if recent:
        lines.append("")
        lines.append("### Recently changed entities")
        for e in recent:
            lines.append(f"- {e.friendly_name} ({e.entity_id}) = {e.state} (at {e.last_changed.isoformat()})")

    return "\n".join(lines)


async def _safe_load(
    name: str, loader, db: AsyncSession
) -> str:
    try:
        return await loader(db)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "prompt_assembler_section_failed",
            extra={"section": name, "error": str(e)},
        )
        return (
            f"## {name.title()}\n"
            f"(live network state for this section could not be loaded)"
        )


async def _load_known_names(db: AsyncSession) -> set[str]:
    """Return the set of known device hostnames + service names that the
    referent resolver can match against. Failures in either query return
    a partial set rather than raising."""
    names: set[str] = set()
    try:
        result = await db.execute(
            select(Device.hostname).where(Device.hostname.isnot(None))
        )
        names.update(r[0] for r in result.all() if r[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("known_names_devices_failed", extra={"error": str(e)})
    try:
        result = await db.execute(
            select(ServiceDefinition.name).where(
                ServiceDefinition.enabled.is_(True)
            )
        )
        names.update(r[0] for r in result.all() if r[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("known_names_services_failed", extra={"error": str(e)})
    return names


def _resolve_referent(
    new_content: str,
    prior_messages: list[dict[str, Any]],
    known_names: set[str],
) -> str | None:
    """Return a rewritten version of `new_content` with the referent made
    explicit, or None if no rewrite should happen.

    Behavior:
    - Skip if the query is long (>200 chars) — likely has its own context.
    - Skip if the query already contains an explicit IP or a known name.
    - Skip if the query doesn't contain a pronoun / demonstrative.
    - Otherwise, walk prior messages for the most recent assistant turn,
      extract the first IP mentioned (most specific anchor) or fall back
      to the first known name, and append a parenthetical referent hint.

    Uses "first IP" rather than "last IP" because the subject of a
    typical answer ("The slowest device is 192.168.10.143, as it...") is
    almost always the earliest IP in the reply.
    """
    if len(new_content) > _REFERENT_MAX_QUERY_CHARS:
        return None

    # Explicit IP in the query → user is already being specific.
    if _IPV4_PATTERN.search(new_content):
        return None

    # Explicit known hostname/service name in the query → also specific.
    content_lower = new_content.lower()
    for name in known_names:
        if re.search(rf"\b{re.escape(name.lower())}\b", content_lower):
            return None

    if not _PRONOUN_PATTERN.search(new_content):
        return None

    # Find the most recent assistant message.
    prior_assistant_content: str | None = None
    for m in reversed(prior_messages):
        if m.get("role") == "assistant":
            prior_assistant_content = m.get("content") or ""
            break
    if not prior_assistant_content:
        return None

    # Prefer IP addresses as the anchor — most specific, unambiguous.
    ips = _IPV4_PATTERN.findall(prior_assistant_content)
    if ips:
        referent = ips[0]
        logger.info(
            "referent_resolved",
            extra={
                "anchor_type": "ip",
                "referent": referent,
                "query_chars": len(new_content),
            },
        )
        return (
            f"{new_content} "
            f"(in the context of your previous answer about {referent})"
        )

    # Fallback: earliest known name mentioned in the prior assistant turn.
    prior_lower = prior_assistant_content.lower()
    best: tuple[int, str] | None = None
    for name in known_names:
        pos = prior_lower.find(name.lower())
        if pos >= 0 and (best is None or pos < best[0]):
            best = (pos, name)
    if best is not None:
        logger.info(
            "referent_resolved",
            extra={
                "anchor_type": "name",
                "referent": best[1],
                "query_chars": len(new_content),
            },
        )
        return (
            f"{new_content} "
            f"(in the context of your previous answer about {best[1]})"
        )

    return None


async def assemble_chat_messages(
    db: AsyncSession,
    conversation_id: int,
    new_user_content: str,
) -> list[dict[str, Any]]:
    """Assemble the Ollama /api/chat messages list for a new turn.

    Returns a list of {role, content} dicts: one system message with the
    grounded network-state prompt, followed by all prior messages in the
    conversation (user + assistant), followed by the new user message.
    """
    # Per-section safe loads — any single failure degrades only that section.
    devices_md = await _safe_load("devices", _load_devices_section, db)
    services_md = await _safe_load("services", _load_services_section, db)
    alerts_md = await _safe_load("alerts", _load_alerts_section, db)
    notes_md = await _safe_load("admin notes", _load_notes_section, db)
    events_md = await _safe_load("events", _load_events_section, db)

    sections: list[str] = [SYSTEM_PREAMBLE, devices_md, services_md, alerts_md, notes_md, events_md]

    # Home Assistant grounding is classifier-gated (research R9): include it
    # only when the user's question hints at IoT / Thread / HA topics.
    if _query_is_iot_related(new_user_content):
        ha_md = await _safe_load("home assistant", _load_home_assistant_section, db)
        sections.append(ha_md)

    system_content = "\n\n".join(sections)

    # Load prior messages for this conversation. Exclude empty assistant
    # shells (content=='' and finished_at IS NULL) which represent the
    # in-flight turn we are currently assembling for.
    conv_result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalars().first()
    prior: list[dict[str, str]] = []
    if conv is not None:
        for m in conv.messages:
            # Drop the empty assistant shell row that the router inserts
            # for the current in-flight turn.
            if m.role == "assistant" and m.content == "" and m.finished_at is None:
                continue
            prior.append({"role": m.role, "content": m.content})

    # The chat router inserts the user row for this turn before calling us,
    # so the last entry in `prior` is the new user message. Drop it — we
    # append new_user_content explicitly below so it is guaranteed last.
    if prior and prior[-1]["role"] == "user" and prior[-1]["content"] == new_user_content:
        prior.pop()

    # Referent resolution: on short follow-up questions with pronouns, make
    # the anchor entity explicit for the LLM. Only affects what Ollama sees;
    # the user's original message remains unchanged in the database.
    known_names = await _load_known_names(db)
    rewritten = _resolve_referent(new_user_content, prior, known_names)
    final_user_content = rewritten if rewritten is not None else new_user_content

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    messages.extend(prior)
    messages.append({"role": "user", "content": final_user_content})

    # Defensive size check — trim oldest prior messages if the total exceeds
    # the character budget. Never trim the system message or the new user
    # message; always remove from the front of `prior` first.
    def total_chars(msgs: list[dict[str, Any]]) -> int:
        return sum(len(m["content"]) for m in msgs)

    if total_chars(messages) > MAX_PROMPT_CHARS:
        logger.warning(
            "prompt_too_large",
            extra={
                "conversation_id": conversation_id,
                "chars": total_chars(messages),
                "limit": MAX_PROMPT_CHARS,
            },
        )
        # messages[0] is system, messages[-1] is new user; trim messages[1:-1].
        while total_chars(messages) > MAX_PROMPT_CHARS and len(messages) > 2:
            del messages[1]

    return messages
