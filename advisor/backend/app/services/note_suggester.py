"""LLM-powered note suggestion extraction.

Given a conversation's messages, asks Ollama to extract 0–3 durable facts
worth saving as admin notes. Filters out previously rejected suggestions
by content hash.
"""

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rejected_suggestion import RejectedSuggestion
from app.services.ollama_client import OllamaUnreachableError, stream_chat

logger = logging.getLogger(__name__)

SUGGESTION_SYSTEM_PROMPT = """You are analyzing a conversation between a network administrator and their network advisor.

Extract 0–3 facts about the admin's network that would be worth saving as durable notes. Only extract facts the admin explicitly stated — do not infer or speculate. Focus on:
- Device quirks, schedules, or maintenance windows
- Service configuration details or upgrade history
- Network-wide conventions, contacts, or vendor details

Return a JSON array of objects with these fields:
- "target_type": one of "device", "service", or "playbook"
- "target_id": integer device or service ID if known, otherwise null
- "target_label": human-readable name of the device or service, or null for playbook
- "body": the note text to save

Return [] if nothing is worth saving. Return ONLY the JSON array, no other text."""


def _hash_body(body: str) -> str:
    normalised = " ".join(body.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()


async def generate_suggestions(
    db: AsyncSession,
    conversation_messages: list[dict[str, str]],
) -> list[dict]:
    """Extract note suggestions from conversation via LLM.

    Returns a list of suggestion dicts: {target_type, target_id, target_label, body}.
    Returns [] if Ollama is unreachable or no suggestions are found.
    Filters out suggestions whose content hash matches a rejected_suggestions entry.
    """
    if not conversation_messages:
        return []

    # Build the extraction prompt with conversation context.
    messages = [
        {"role": "system", "content": SUGGESTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Here is the conversation to analyze:\n\n"
                + "\n".join(
                    f"[{m['role']}]: {m['content']}"
                    for m in conversation_messages
                    if m.get("content")
                )
                + "\n\nExtract 0–3 durable facts as a JSON array."
            ),
        },
    ]

    # Collect the full response (non-streaming consumption).
    try:
        chunks: list[str] = []
        async for chunk in stream_chat(messages):
            chunks.append(chunk)
        raw = "".join(chunks).strip()
    except OllamaUnreachableError:
        logger.warning("note_suggester_ollama_unreachable")
        return []

    # Parse JSON — handle markdown code fences the model might wrap it in.
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        suggestions = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "note_suggester_bad_json",
            extra={"raw": raw[:500]},
        )
        return []

    if not isinstance(suggestions, list):
        return []

    # Validate each suggestion has required fields.
    valid = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        body = s.get("body")
        if not body or not isinstance(body, str):
            continue
        valid.append({
            "target_type": s.get("target_type", "playbook"),
            "target_id": s.get("target_id"),
            "target_label": s.get("target_label"),
            "body": body,
        })

    # Filter out previously rejected suggestions by content hash.
    if valid:
        hashes = [_hash_body(s["body"]) for s in valid]
        result = await db.execute(
            select(RejectedSuggestion.content_hash).where(
                RejectedSuggestion.content_hash.in_(hashes)
            )
        )
        rejected_hashes = {row[0] for row in result.all()}
        valid = [
            s for s, h in zip(valid, hashes) if h not in rejected_hashes
        ]

    # Cap at 3 suggestions.
    return valid[:3]
