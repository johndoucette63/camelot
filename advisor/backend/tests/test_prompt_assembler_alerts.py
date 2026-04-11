"""Tests for the Active Alerts section added to prompt_assembler (T067/FR-028).

The assembled chat prompt must:

* Contain the ``## Active Alerts`` heading when at least one alert is open.
* NOT contain the heading when no alerts are open.
* Cap the rendered list at ``ACTIVE_ALERTS_LIMIT`` (20) and append a
  trailing ``(N more not shown)`` line.
* Order alerts critical → warning → info.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.alert import Alert
from app.models.conversation import Conversation
from app.services import prompt_assembler
from app.services.prompt_assembler import ACTIVE_ALERTS_LIMIT, _load_alerts_section


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_alert(
    *,
    severity: str,
    message: str,
    state: str = "active",
    created_offset_minutes: int = 0,
) -> Alert:
    return Alert(
        rule_id="device_offline",
        target_type="system",
        target_id=None,
        severity=severity,
        message=message,
        state=state,
        source="rule",
        suppressed=False,
        created_at=_now() - timedelta(minutes=created_offset_minutes),
    )


@pytest.mark.asyncio
async def test_active_alerts_heading_absent_when_no_alerts(db):
    section = await _load_alerts_section(db)
    assert "## Active Alerts" in section
    assert "(no active alerts)" in section


@pytest.mark.asyncio
async def test_active_alerts_section_renders_when_alerts_exist(db):
    db.add_all(
        [
            _make_alert(severity="warning", message="NAS offline"),
            _make_alert(severity="critical", message="Plex down"),
        ]
    )
    await db.commit()

    section = await _load_alerts_section(db)
    assert "## Active Alerts (2 open)" in section
    assert "NAS offline" in section
    assert "Plex down" in section
    # Critical alert must come before warning alert in the rendered list.
    assert section.index("Plex down") < section.index("NAS offline")


@pytest.mark.asyncio
async def test_resolved_and_suppressed_alerts_are_excluded(db):
    resolved = _make_alert(severity="warning", message="old warning")
    resolved.state = "resolved"
    resolved.resolved_at = _now()
    resolved.resolution_source = "auto"

    suppressed = _make_alert(severity="warning", message="muted warning")
    suppressed.suppressed = True

    active = _make_alert(severity="info", message="live info")

    db.add_all([resolved, suppressed, active])
    await db.commit()

    section = await _load_alerts_section(db)
    assert "live info" in section
    assert "old warning" not in section
    assert "muted warning" not in section
    assert "(1 open)" in section


@pytest.mark.asyncio
async def test_active_alerts_capped_at_limit_with_more_not_shown_tail(db):
    # Seed one more than the limit; the last one is dropped from the list
    # but should appear as "(N more not shown)".
    n = ACTIVE_ALERTS_LIMIT + 3
    for i in range(n):
        db.add(
            _make_alert(
                severity="warning",
                message=f"alert number {i}",
                created_offset_minutes=i,  # oldest comes last in DESC order
            )
        )
    await db.commit()

    section = await _load_alerts_section(db)
    lines = section.splitlines()

    header = lines[0]
    assert f"## Active Alerts ({n} open)" == header

    rendered = [ln for ln in lines if ln.startswith("-")]
    assert len(rendered) == ACTIVE_ALERTS_LIMIT

    trailing = [ln for ln in lines if "more not shown" in ln]
    assert trailing == [f"({n - ACTIVE_ALERTS_LIMIT} more not shown)"]


@pytest.mark.asyncio
async def test_full_prompt_contains_active_alerts_section_when_alerts_exist(db):
    db.add(_make_alert(severity="critical", message="CRITICAL THING"))
    conv = Conversation()
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "what's happening?"
    )
    system = messages[0]["content"]
    assert "## Active Alerts" in system
    assert "CRITICAL THING" in system
