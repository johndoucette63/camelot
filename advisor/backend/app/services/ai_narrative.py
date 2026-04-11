"""AI-assisted narrative layer for the recommendations panel.

Takes a list of currently-active rule-based alerts and asks Ollama to
produce a short consolidated explanation. Degrades gracefully (returns
``None``) if Ollama is slow, unreachable, or returns garbage — the
rule-based recommendations continue to render normally per FR-020.

The narrative result is cached in-process keyed by the sorted tuple of
active alert IDs, with a short TTL so a dashboard polling every 30 s
does not re-hit Ollama on every call.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level cache: {cache_key -> (stored_at_monotonic, result_dict)}.
_NARRATIVE_CACHE: dict[tuple[int, ...], tuple[float, dict]] = {}

ANTI_FABRICATION_INSTRUCTIONS = (
    "STRICT RULES: (1) Do not invent alerts. "
    "(2) Only reference alerts provided below — you must not add alerts "
    "that are not in the list. (3) If an alert is not in the list, do not "
    "mention it. (4) Keep the response under 120 words."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _cache_key(alert_ids: Iterable[int]) -> tuple[int, ...]:
    return tuple(sorted(alert_ids))


def build_prompt(active_alerts: list) -> str:
    """Build the Ollama prompt from the active alerts list.

    Kept as a pure function so tests can assert against the constructed
    prompt without having to mock the HTTP call. Satisfies FR-021 at the
    prompt-construction layer: the prompt must explicitly forbid
    invented alerts and enumerate the exact alert IDs provided.
    """
    lines = [
        "You are the AI assistant for a home infrastructure monitoring dashboard.",
        "A rule-based engine has already determined which alerts are firing.",
        "Your job is to consolidate them into a short, helpful narrative for the",
        "admin that explains what is happening and, if there is an obvious",
        "correlation, names it.",
        "",
        ANTI_FABRICATION_INSTRUCTIONS,
        "",
        "ACTIVE ALERTS:",
    ]
    for alert in active_alerts:
        lines.append(
            f"- [id={alert.id}] [{alert.severity}] {alert.rule_id}: {alert.message}"
        )
    lines.append("")
    lines.append("Write the narrative now.")
    return "\n".join(lines)


async def _call_ollama(prompt: str, timeout_seconds: float) -> str | None:
    url = f"{settings.ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "ai_narrative.call.failed",
                extra={
                    "event": "ai_narrative.call.failed",
                    "status_code": resp.status_code,
                    "error": resp.text[:200],
                },
            )
            return None
        body = resp.json()
        text = (body.get("response") or "").strip()
        return text or None
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.warning(
            "ai_narrative.call.failed",
            extra={"event": "ai_narrative.call.failed", "error": str(exc)},
        )
        return None


async def get_narrative(active_alerts: list) -> dict | None:
    """Return a narrative dict, or ``None`` if unavailable."""
    if not active_alerts:
        return None

    key = _cache_key(a.id for a in active_alerts)
    now_mono = time.monotonic()
    cache_ttl = float(settings.ai_narrative_cache_seconds)

    cached = _NARRATIVE_CACHE.get(key)
    if cached is not None and (now_mono - cached[0]) < cache_ttl:
        return cached[1]

    t0 = time.monotonic()
    prompt = build_prompt(active_alerts)
    text = await _call_ollama(prompt, float(settings.ai_narrative_timeout_seconds))
    latency_ms = int((time.monotonic() - t0) * 1000)

    if text is None:
        return None

    result = {
        "text": text,
        "generated_at": _utcnow().isoformat() + "Z",
        "source": "ollama",
    }
    _NARRATIVE_CACHE[key] = (now_mono, result)

    logger.info(
        "ai_narrative.call.ok",
        extra={
            "event": "ai_narrative.call.ok",
            "latency_ms": latency_ms,
            "alert_count": len(active_alerts),
        },
    )
    return result
