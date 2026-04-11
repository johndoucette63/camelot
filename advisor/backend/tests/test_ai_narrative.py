"""Tests for app.services.ai_narrative (User Story 4).

Cover build_prompt (anti-fabrication structure + alert enumeration),
get_narrative (happy path, cache hit, timeout, connect error, cache key
uniqueness). The real _call_ollama is patched away so nothing in the
test suite ever touches the network.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.services import ai_narrative
from app.services.ai_narrative import (
    ANTI_FABRICATION_INSTRUCTIONS,
    _NARRATIVE_CACHE,
    build_prompt,
    get_narrative,
)


def _make_alert(
    *,
    id: int,
    severity: str = "warning",
    rule_id: str = "disk_high",
    message: str = "disk full",
):
    return SimpleNamespace(
        id=id, severity=severity, rule_id=rule_id, message=message
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test starts with a clean cache."""
    _NARRATIVE_CACHE.clear()
    yield
    _NARRATIVE_CACHE.clear()


# ── build_prompt structure ─────────────────────────────────────────────


def test_build_prompt_contains_anti_fabrication_instructions():
    """FR-021: the prompt must contain the verbatim anti-fabrication block."""
    alerts = [_make_alert(id=1, message="m1")]
    prompt = build_prompt(alerts)

    # Structural assertion — the whole block must be present verbatim.
    assert ANTI_FABRICATION_INSTRUCTIONS in prompt

    lowered = prompt.lower()
    assert "do not invent" in lowered
    assert "only reference" in lowered
    assert "must not" in lowered


def test_build_prompt_lists_same_alert_ids_no_drops_or_additions():
    alerts = [
        _make_alert(id=7, severity="critical", rule_id="service_down", message="plex"),
        _make_alert(id=42, severity="warning", rule_id="disk_high", message="nas 97%"),
        _make_alert(id=13, severity="info", rule_id="ollama_unavailable", message="ollama"),
    ]
    prompt = build_prompt(alerts)

    # Every input alert id must appear exactly once.
    for alert in alerts:
        assert f"[id={alert.id}]" in prompt
        assert prompt.count(f"[id={alert.id}]") == 1

    # And no stray alert IDs should sneak in.
    # Count total "[id=" markers equals number of input alerts.
    assert prompt.count("[id=") == len(alerts)

    # Severity and rule_id labels are both present for each alert.
    for alert in alerts:
        assert f"[{alert.severity}]" in prompt
        assert f"{alert.rule_id}:" in prompt
        assert alert.message in prompt


# ── get_narrative happy path and cache ─────────────────────────────────


@pytest.mark.asyncio
async def test_get_narrative_happy_path(monkeypatch):
    calls = {"n": 0}

    async def fake_call_ollama(prompt, timeout_seconds):
        calls["n"] += 1
        return "some narrative text"

    monkeypatch.setattr(ai_narrative, "_call_ollama", fake_call_ollama)

    alerts = [_make_alert(id=1), _make_alert(id=2)]
    result = await get_narrative(alerts)

    assert result is not None
    assert result["text"] == "some narrative text"
    assert result["source"] == "ollama"
    assert "generated_at" in result and isinstance(result["generated_at"], str)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_get_narrative_cache_hit_skips_second_call(monkeypatch):
    calls = {"n": 0}

    async def fake_call_ollama(prompt, timeout_seconds):
        calls["n"] += 1
        return "cached text"

    monkeypatch.setattr(ai_narrative, "_call_ollama", fake_call_ollama)

    alerts = [_make_alert(id=1), _make_alert(id=2)]
    first = await get_narrative(alerts)
    second = await get_narrative(alerts)

    assert calls["n"] == 1, "second call with same alert IDs must hit cache"
    assert first == second
    assert first is not None


@pytest.mark.asyncio
async def test_get_narrative_cache_key_differs_per_alert_set(monkeypatch):
    calls = {"n": 0}

    async def fake_call_ollama(prompt, timeout_seconds):
        calls["n"] += 1
        return f"narrative #{calls['n']}"

    monkeypatch.setattr(ai_narrative, "_call_ollama", fake_call_ollama)

    r1 = await get_narrative([_make_alert(id=1)])
    r2 = await get_narrative([_make_alert(id=1), _make_alert(id=2)])
    r3 = await get_narrative([_make_alert(id=2)])

    assert calls["n"] == 3
    assert r1["text"] == "narrative #1"
    assert r2["text"] == "narrative #2"
    assert r3["text"] == "narrative #3"

    # Re-fetching the first set still hits the cache.
    r1_again = await get_narrative([_make_alert(id=1)])
    assert calls["n"] == 3
    assert r1_again == r1


# ── get_narrative error paths ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_narrative_timeout_returns_none(monkeypatch):
    """Exercise the real _call_ollama, stubbing the httpx post layer."""

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    alerts = [_make_alert(id=1)]
    result = await get_narrative(alerts)
    assert result is None


@pytest.mark.asyncio
async def test_get_narrative_connect_error_returns_none(monkeypatch):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("simulated connect refused")

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    alerts = [_make_alert(id=1)]
    result = await get_narrative(alerts)
    assert result is None


@pytest.mark.asyncio
async def test_get_narrative_empty_alerts_returns_none():
    assert await get_narrative([]) is None
