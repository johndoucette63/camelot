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
from app.models.conversation import Conversation
from app.models.device import Device
from app.models.event import Event
from app.models.health_check_result import HealthCheckResult
from app.models.service_definition import ServiceDefinition

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
- If the referent is genuinely ambiguous, ask the user which entity they mean rather than guessing."""


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
    events_md = await _safe_load("events", _load_events_section, db)

    system_content = "\n\n".join(
        [SYSTEM_PREAMBLE, devices_md, services_md, alerts_md, events_md]
    )

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
