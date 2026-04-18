"""Tests for the Home Assistant grounding block in prompt_assembler (T063).

Covers FR-009 + SC-006: the HA snapshot is surfaced to the AI chat pipeline
only when the user's question is IoT-related, and the block is bounded at
20 recently-changed entities.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.thread_border_router import ThreadBorderRouter
from app.models.thread_device import ThreadDevice
from app.services.prompt_assembler import assemble_chat_messages


async def _ensure_connection(db: AsyncSession, configured: bool = True) -> None:
    """Seed the singleton HA connection row."""
    conn = await db.get(HomeAssistantConnection, 1)
    if conn is None:
        conn = HomeAssistantConnection(id=1)
        db.add(conn)
    if configured:
        conn.base_url = "http://homeassistant.local:8123"
        conn.token_ciphertext = b"fake-ciphertext"
        conn.last_success_at = datetime.now(tz=timezone.utc) - timedelta(seconds=12)
        conn.last_error = None
    else:
        conn.base_url = None
        conn.token_ciphertext = None
        conn.last_success_at = None
        conn.last_error = None
    await db.commit()


async def _seed_ha_snapshot(db: AsyncSession, n_entities: int = 25) -> None:
    """Seed `n_entities` entity snapshots, one border router, and one device."""
    now = datetime.now(tz=timezone.utc)
    for i in range(n_entities):
        db.add(
            HAEntitySnapshot(
                entity_id=f"binary_sensor.test_{i}",
                ha_device_id=f"dev-{i}",
                domain="binary_sensor",
                friendly_name=f"Test Sensor {i}",
                state="on" if i % 2 == 0 else "off",
                last_changed=now - timedelta(minutes=i),
                attributes={},
                polled_at=now,
            )
        )
    db.add(
        ThreadBorderRouter(
            ha_device_id="br-kitchen",
            friendly_name="HomePod mini – Kitchen",
            model="HomePod mini",
            online=True,
            attached_device_count=5,
            last_refreshed_at=now,
        )
    )
    db.add(
        ThreadDevice(
            ha_device_id="aqara-motion-hall",
            friendly_name="Aqara Motion – Hall",
            parent_border_router_id="br-kitchen",
            online=True,
            last_seen_parent_id="br-kitchen",
            last_refreshed_at=now,
        )
    )
    await db.commit()


async def _new_conversation(db: AsyncSession) -> int:
    conv = Conversation(title="test")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv.id


@pytest.mark.asyncio
async def test_iot_query_includes_ha_section(db: AsyncSession) -> None:
    """IoT-tagged question → HA grounding block appears in the system prompt."""
    await _ensure_connection(db, configured=True)
    await _seed_ha_snapshot(db, n_entities=5)
    conv_id = await _new_conversation(db)

    messages = await assemble_chat_messages(
        db,
        conversation_id=conv_id,
        new_user_content="Which of my Thread border routers have the most devices attached?",
    )

    system_content = messages[0]["content"]
    assert "## Home Assistant" in system_content
    assert "Thread border routers:" in system_content
    assert "Thread devices:" in system_content


@pytest.mark.asyncio
async def test_non_iot_query_excludes_ha_section(db: AsyncSession) -> None:
    """Non-IoT question → HA block NOT in the prompt (avoids pollution)."""
    await _ensure_connection(db, configured=True)
    await _seed_ha_snapshot(db, n_entities=5)
    conv_id = await _new_conversation(db)

    messages = await assemble_chat_messages(
        db,
        conversation_id=conv_id,
        new_user_content="What is the status of Plex right now?",
    )

    system_content = messages[0]["content"]
    assert "## Home Assistant" not in system_content


@pytest.mark.asyncio
async def test_ha_section_bounded_at_20_entities(db: AsyncSession) -> None:
    """A rich HA install yields at most 20 recently-changed entities in the block."""
    await _ensure_connection(db, configured=True)
    await _seed_ha_snapshot(db, n_entities=50)
    conv_id = await _new_conversation(db)

    messages = await assemble_chat_messages(
        db,
        conversation_id=conv_id,
        new_user_content="Show me the state of my Aqara sensors.",
    )

    system_content = messages[0]["content"]
    # Each listed entity renders as a "- <friendly_name> (<entity_id>) = ..."
    # Count occurrences of the entity-row prefix within the HA section.
    ha_section = system_content.split("## Home Assistant", 1)[1]
    entity_lines = [ln for ln in ha_section.splitlines() if ln.startswith("- Test Sensor ")]
    assert len(entity_lines) == 20


@pytest.mark.asyncio
async def test_unconfigured_connection_emits_placeholder(db: AsyncSession) -> None:
    """No HA connection configured → placeholder line, no crash."""
    await _ensure_connection(db, configured=False)
    conv_id = await _new_conversation(db)

    messages = await assemble_chat_messages(
        db,
        conversation_id=conv_id,
        new_user_content="Anything wrong with my HomeKit devices?",
    )

    system_content = messages[0]["content"]
    assert "## Home Assistant" in system_content
    assert "no Home Assistant connection configured" in system_content
