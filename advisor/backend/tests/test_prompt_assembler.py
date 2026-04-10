"""Tests for the prompt assembler.

Seeds devices, services, alerts, and events into the test DB and asserts the
assembled system prompt contains the expected substrings and frame shape.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.alert import Alert
from app.models.annotation import Annotation
from app.models.conversation import Conversation
from app.models.device import Device
from app.models.event import Event
from app.models.health_check_result import HealthCheckResult
from app.models.message import Message
from app.models.service_definition import ServiceDefinition
from app.services import prompt_assembler

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.utcnow()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed_basic(db: AsyncSession) -> Conversation:
    holygrail = Device(
        mac_address="aa:bb:cc:dd:ee:01",
        ip_address="192.168.10.129",
        hostname="HOLYGRAIL",
        first_seen=_now(),
        last_seen=_now(),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=True,
    )
    nas = Device(
        mac_address="aa:bb:cc:dd:ee:02",
        ip_address="192.168.10.105",
        hostname="nas",
        first_seen=_now(),
        last_seen=_now(),
        is_online=False,
        consecutive_missed_scans=3,
        is_known_device=True,
    )
    db.add_all([holygrail, nas])
    await db.flush()
    db.add(Annotation(device_id=holygrail.id, role="server", tags=["media", "ai"]))
    db.add(Annotation(device_id=nas.id, role="nas", tags=["storage"]))

    plex = ServiceDefinition(
        name="Plex",
        host_label="HOLYGRAIL",
        host="192.168.10.129",
        port=32400,
        check_type="http",
        check_url="/identity",
        check_interval_seconds=60,
        enabled=True,
    )
    deluge = ServiceDefinition(
        name="Deluge",
        host_label="Torrentbox",
        host="192.168.10.141",
        port=8112,
        check_type="http",
        check_url="/",
        check_interval_seconds=60,
        enabled=True,
    )
    db.add_all([plex, deluge])
    await db.flush()

    db.add(HealthCheckResult(service_id=plex.id, checked_at=_now(), status="up", response_time_ms=42))
    db.add(
        HealthCheckResult(
            service_id=deluge.id,
            checked_at=_now(),
            status="down",
            error="connection refused",
        )
    )

    db.add(
        Alert(
            device_id=nas.id,
            severity="warning",
            message="NAS has been offline for 3 scans",
            created_at=_now() - timedelta(hours=2),
            acknowledged=False,
        )
    )
    # Stale alert — should NOT appear in the 24h window.
    db.add(
        Alert(
            device_id=nas.id,
            severity="info",
            message="An old advisory from three days ago",
            created_at=_now() - timedelta(hours=72),
            acknowledged=True,
        )
    )

    db.add(
        Event(
            event_type="offline",
            device_id=nas.id,
            timestamp=_now() - timedelta(hours=1),
            details={"reason": "no response"},
        )
    )
    db.add(
        Event(
            event_type="back-online",
            device_id=holygrail.id,
            timestamp=_now() - timedelta(hours=48),
            details=None,
        )
    )

    conversation = Conversation()
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@pytest.mark.asyncio
async def test_devices_section_lists_all_with_online_state(db):
    conv = await _seed_basic(db)
    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "what devices are on my network?"
    )
    system = messages[0]["content"]
    assert "HOLYGRAIL" in system
    assert "192.168.10.129" in system
    assert "nas" in system
    assert "OFFLINE" in system
    assert "ONLINE" in system
    assert "1/2 online" in system  # 1 online out of 2 devices


@pytest.mark.asyncio
async def test_services_section_marks_unhealthy(db):
    conv = await _seed_basic(db)
    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "which services are down?"
    )
    system = messages[0]["content"]
    assert "Plex" in system
    assert "UP" in system
    assert "Deluge" in system
    assert "DOWN" in system
    assert "connection refused" in system


@pytest.mark.asyncio
async def test_alerts_section_includes_only_last_24_hours(db):
    conv = await _seed_basic(db)
    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "what alerts?"
    )
    system = messages[0]["content"]
    assert "NAS has been offline" in system
    assert "three days ago" not in system


@pytest.mark.asyncio
async def test_new_user_message_is_last(db):
    conv = await _seed_basic(db)
    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "how many devices are offline?"
    )
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "how many devices are offline?"
    assert messages[0]["role"] == "system"


@pytest.mark.asyncio
async def test_prior_messages_appended_in_chronological_order(db):
    conv = await _seed_basic(db)
    # Seed two prior turns manually.
    db.add_all(
        [
            Message(
                conversation_id=conv.id, role="user", content="first question",
                created_at=_now() - timedelta(minutes=10),
            ),
            Message(
                conversation_id=conv.id, role="assistant", content="first answer",
                created_at=_now() - timedelta(minutes=9),
                finished_at=_now() - timedelta(minutes=9),
            ),
            Message(
                conversation_id=conv.id, role="user", content="second question",
                created_at=_now() - timedelta(minutes=5),
            ),
            Message(
                conversation_id=conv.id, role="assistant", content="second answer",
                created_at=_now() - timedelta(minutes=4),
                finished_at=_now() - timedelta(minutes=4),
            ),
        ]
    )
    await db.commit()

    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "third question"
    )
    # Strip the system message for easier assertion.
    dialogue = [(m["role"], m["content"]) for m in messages if m["role"] != "system"]
    assert dialogue == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "second question"),
        ("assistant", "second answer"),
        ("user", "third question"),
    ]


@pytest.mark.asyncio
async def test_empty_assistant_shell_is_filtered_out(db):
    conv = await _seed_basic(db)
    # Simulate the router's insertion of the in-flight assistant shell.
    db.add_all(
        [
            Message(
                conversation_id=conv.id,
                role="user",
                content="in-flight question",
                created_at=_now(),
            ),
            Message(
                conversation_id=conv.id,
                role="assistant",
                content="",
                created_at=_now(),
                finished_at=None,
            ),
        ]
    )
    await db.commit()

    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "in-flight question"
    )
    # The empty assistant shell must not appear. The new user question
    # must be exactly one entry in the final messages list.
    assert not any(
        m["role"] == "assistant" and m["content"] == "" for m in messages
    )
    assert messages[-1] == {"role": "user", "content": "in-flight question"}
    user_entries = [m for m in messages if m["role"] == "user"]
    assert len(user_entries) == 1


@pytest.mark.asyncio
async def test_degrades_gracefully_when_devices_query_fails(db, monkeypatch):
    conv = await _seed_basic(db)

    async def boom(db_):
        raise RuntimeError("simulated inventory outage")

    monkeypatch.setattr(prompt_assembler, "_load_devices_section", boom)

    # Must not raise.
    messages = await prompt_assembler.assemble_chat_messages(
        db, conv.id, "what devices are on my network?"
    )
    system = messages[0]["content"]
    assert "could not be loaded" in system
    # Other sections should still render.
    assert "Plex" in system


@pytest.mark.asyncio
async def test_warns_and_trims_when_prompt_exceeds_max_chars(db, monkeypatch, caplog):
    conv = await _seed_basic(db)
    # Seed many large prior messages to exceed the limit.
    big = "x" * 10_000
    for i in range(10):
        db.add(
            Message(
                conversation_id=conv.id,
                role="user" if i % 2 == 0 else "assistant",
                content=big,
                created_at=_now() - timedelta(minutes=30 - i),
                finished_at=_now() - timedelta(minutes=30 - i),
            )
        )
    await db.commit()

    monkeypatch.setattr(prompt_assembler, "MAX_PROMPT_CHARS", 20_000)

    import logging
    with caplog.at_level(logging.WARNING):
        messages = await prompt_assembler.assemble_chat_messages(
            db, conv.id, "new question"
        )

    assert any("prompt_too_large" in rec.message for rec in caplog.records)
    # System and new user are preserved; some prior messages were trimmed.
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "new question"
    total_chars = sum(len(m["content"]) for m in messages)
    assert total_chars <= 20_000
