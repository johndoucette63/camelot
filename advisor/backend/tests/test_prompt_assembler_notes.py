"""Tests for the notes section in prompt_assembler — T019."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.device import Device
from app.models.note import Note

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_notes_section_with_no_notes(db):
    from app.services.prompt_assembler import _load_notes_section

    result = await _load_notes_section(db)
    assert "## Admin Notes" in result
    assert "no admin notes" in result


@pytest.mark.asyncio
async def test_pinned_note_always_included(db):
    from app.services.prompt_assembler import _load_notes_section

    device = Device(
        mac_address="AA:BB:CC:00:00:01",
        ip_address="192.168.10.105",
        hostname="NAS",
        first_seen=_now(),
        last_seen=_now(),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=True,
    )
    db.add(device)
    await db.flush()

    note = Note(
        target_type="device",
        target_id=device.id,
        body="Scheduled RAID scrub every Sunday 2AM",
        pinned=True,
    )
    db.add(note)
    await db.commit()

    result = await _load_notes_section(db)
    assert "## Admin Notes" in result
    assert "[pinned]" in result
    assert "RAID scrub" in result
    assert "NAS" in result


@pytest.mark.asyncio
async def test_playbook_entry_shows_title(db):
    from app.services.prompt_assembler import _load_notes_section

    note = Note(
        target_type="playbook",
        title="VPN Rotation",
        body="Credentials rotate first Monday of every month",
        pinned=False,
    )
    db.add(note)
    await db.commit()

    result = await _load_notes_section(db)
    assert "Playbook: VPN Rotation" in result
    assert "Credentials rotate" in result


@pytest.mark.asyncio
async def test_attribution_labels_present(db):
    from app.services.prompt_assembler import _load_notes_section

    device = Device(
        mac_address="DD:EE:FF:00:00:01",
        ip_address="192.168.10.129",
        hostname="HOLYGRAIL",
        first_seen=_now(),
        last_seen=_now(),
        is_online=True,
        consecutive_missed_scans=0,
        is_known_device=True,
    )
    db.add(device)
    await db.flush()

    db.add(Note(target_type="device", target_id=device.id, body="Test note", pinned=True))
    db.add(Note(target_type="playbook", title="My Playbook", body="PB content", pinned=True))
    await db.commit()

    result = await _load_notes_section(db)
    assert "### Device: HOLYGRAIL" in result
    assert "### Playbook: My Playbook" in result


@pytest.mark.asyncio
async def test_graceful_degradation(db):
    from app.services.prompt_assembler import _safe_load

    async def _failing_loader(db):
        raise RuntimeError("DB connection lost")

    result = await _safe_load("admin notes", _failing_loader, db)
    assert "could not be loaded" in result
