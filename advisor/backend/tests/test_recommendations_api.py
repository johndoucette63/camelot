"""Tests for GET /recommendations."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.alert import Alert
from app.routers import recommendations as recs_module

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _stub_ai_narrative(monkeypatch):
    """Default to a null narrative so tests never hit real Ollama.

    Individual tests that want to exercise the populated path can override
    this with their own monkeypatch.setattr call (see the US4 tests).
    """
    from app.services import ai_narrative as ai_narrative_module

    async def _return_none(alerts):
        return None

    monkeypatch.setattr(ai_narrative_module, "get_narrative", _return_none)
    yield


@pytest_asyncio.fixture
async def db_and_override():
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

    # The recommendations router uses `async_session` directly (not a
    # dependency). Monkeypatch the module-level reference.
    original = recs_module.async_session
    recs_module.async_session = session_factory

    async with session_factory() as session:
        yield session

    recs_module.async_session = original
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed_alert(
    db: AsyncSession,
    *,
    rule_id: str,
    severity: str,
    message: str,
    state: str = "active",
    suppressed: bool = False,
    target_type: str = "system",
    target_id: int | None = None,
    created_at: datetime | None = None,
) -> Alert:
    alert = Alert(
        rule_id=rule_id,
        target_type=target_type,
        target_id=target_id,
        severity=severity,
        message=message,
        state=state,
        source="rule",
        suppressed=suppressed,
        created_at=created_at or _now(),
    )
    db.add(alert)
    await db.flush()
    return alert


@pytest.mark.asyncio
async def test_recommendations_empty(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "active": [],
        "counts": {"critical": 0, "warning": 0, "info": 0},
        "ai_narrative": None,
    }


@pytest.mark.asyncio
async def test_recommendations_severity_ordering(db_and_override):
    db = db_and_override
    now = _now()
    # Insert one of each severity, timestamped so that within a single
    # severity group we can also assert created_at DESC ordering.
    await _seed_alert(
        db,
        rule_id="ollama_unavailable",
        severity="info",
        message="ollama down",
        created_at=now - timedelta(minutes=3),
    )
    await _seed_alert(
        db,
        rule_id="disk_high",
        severity="warning",
        message="disk high on NAS",
        created_at=now - timedelta(minutes=2),
    )
    await _seed_alert(
        db,
        rule_id="service_down",
        severity="critical",
        message="plex down",
        created_at=now - timedelta(minutes=1),
    )
    # Second warning, more recent, should come before the first warning.
    await _seed_alert(
        db,
        rule_id="disk_high",
        severity="warning",
        message="disk high on mediaserver",
        target_id=2,
        target_type="device",
        created_at=now,
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    assert resp.status_code == 200
    body = resp.json()

    assert body["counts"] == {"critical": 1, "warning": 2, "info": 1}

    active = body["active"]
    assert len(active) == 4
    assert [a["severity"] for a in active] == [
        "critical",
        "warning",
        "warning",
        "info",
    ]
    # Within "warning", the newer one (disk high on mediaserver) first.
    assert active[1]["message"] == "disk high on mediaserver"
    assert active[2]["message"] == "disk high on NAS"

    assert body["ai_narrative"] is None


@pytest.mark.asyncio
async def test_recommendations_counts_match_active_list(db_and_override):
    db = db_and_override
    await _seed_alert(db, rule_id="disk_high", severity="warning", message="w1")
    await _seed_alert(db, rule_id="disk_high", severity="warning", message="w2")
    await _seed_alert(
        db, rule_id="service_down", severity="critical", message="c1"
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    body = resp.json()
    active = body["active"]
    counts = body["counts"]

    assert counts["warning"] == sum(1 for a in active if a["severity"] == "warning")
    assert counts["critical"] == sum(1 for a in active if a["severity"] == "critical")
    assert counts["info"] == sum(1 for a in active if a["severity"] == "info")
    assert len(active) == counts["critical"] + counts["warning"] + counts["info"]


@pytest.mark.asyncio
async def test_recommendations_excludes_suppressed(db_and_override):
    db = db_and_override
    await _seed_alert(
        db,
        rule_id="disk_high",
        severity="warning",
        message="visible",
        suppressed=False,
    )
    await _seed_alert(
        db,
        rule_id="disk_high",
        severity="warning",
        message="muted — should not appear",
        suppressed=True,
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    body = resp.json()
    assert len(body["active"]) == 1
    assert body["active"][0]["message"] == "visible"
    assert body["counts"]["warning"] == 1


@pytest.mark.asyncio
async def test_recommendations_excludes_resolved(db_and_override):
    """Resolved alerts are not part of the active recommendations payload."""
    db = db_and_override
    await _seed_alert(
        db,
        rule_id="disk_high",
        severity="warning",
        message="still active",
    )
    await _seed_alert(
        db,
        rule_id="disk_high",
        severity="critical",
        message="already resolved",
        state="resolved",
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    body = resp.json()
    messages = [a["message"] for a in body["active"]]
    assert "still active" in messages
    assert "already resolved" not in messages
    assert body["counts"]["critical"] == 0


@pytest.mark.asyncio
async def test_recommendations_ai_narrative_null_in_v1(db_and_override):
    """US4 hasn't shipped: ai_narrative module is absent so field must be null."""
    db = db_and_override
    await _seed_alert(
        db, rule_id="disk_high", severity="warning", message="hi"
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    assert resp.json()["ai_narrative"] is None


# ── US4: GET /recommendations includes ai_narrative from get_narrative ──


@pytest.mark.asyncio
async def test_recommendations_includes_ai_narrative_when_present(
    db_and_override, monkeypatch
):
    """When get_narrative returns a dict, the endpoint embeds it verbatim."""
    db = db_and_override
    await _seed_alert(
        db, rule_id="disk_high", severity="warning", message="disk high"
    )
    await db.commit()

    fake_narrative = {
        "text": "x",
        "generated_at": "2026-01-01T00:00:00Z",
        "source": "ollama",
    }

    async def fake_get_narrative(alerts):
        return fake_narrative

    from app.services import ai_narrative as ai_narrative_module

    monkeypatch.setattr(
        ai_narrative_module, "get_narrative", fake_get_narrative
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_narrative"] == fake_narrative
    assert len(body["active"]) == 1


@pytest.mark.asyncio
async def test_recommendations_ai_narrative_null_when_service_returns_none(
    db_and_override, monkeypatch
):
    """When get_narrative returns None, ai_narrative is null and active list still renders."""
    db = db_and_override
    await _seed_alert(
        db, rule_id="service_down", severity="critical", message="plex down"
    )
    await db.commit()

    async def fake_get_narrative(alerts):
        return None

    from app.services import ai_narrative as ai_narrative_module

    monkeypatch.setattr(
        ai_narrative_module, "get_narrative", fake_get_narrative
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_narrative"] is None
    assert len(body["active"]) == 1
    assert body["active"][0]["message"] == "plex down"
