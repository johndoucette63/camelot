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
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
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

SYSTEM_PREAMBLE = """You are the Camelot network advisor, a conversational assistant for a single home administrator managing a small home network.

Answer questions about the user's network using the live state provided below. Always reference real devices and services by their actual names and IP addresses. If the answer cannot be determined from the state below, say so clearly — do not invent devices, services, or facts. Be concise."""


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


async def _load_alerts_section(db: AsyncSession) -> str:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(Alert)
        .options(selectinload(Alert.device), selectinload(Alert.service))
        .where(Alert.created_at >= cutoff)
        .order_by(Alert.created_at.desc())
    )
    alerts = result.scalars().all()
    if not alerts:
        return "## Recent alerts (last 24h)\n(no alerts in the last 24 hours)"

    lines = [f"## Recent alerts (last 24h, {len(alerts)} total)"]
    for a in alerts:
        ts = a.created_at.isoformat() + "Z"
        target = ""
        if a.device is not None:
            target = f" — device={a.device.hostname or a.device.ip_address}"
        if a.service is not None:
            target += f" — service={a.service.name}"
        ack = " [ack]" if a.acknowledged else ""
        lines.append(
            f"- {ts} — {a.severity.upper()}{target} — {a.message}{ack}"
        )
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

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    messages.extend(prior)
    messages.append({"role": "user", "content": new_user_content})

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
