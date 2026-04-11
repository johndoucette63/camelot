"""Tests for US3 alert history log endpoints (GET /alerts, ack, resolve)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.alert import Alert
from app.routers import alerts as alerts_module

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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

    # The alerts router uses `async_session` directly (not a FastAPI
    # dependency). Monkeypatch the module-level reference so it hits our
    # in-memory SQLite test DB.
    original = alerts_module.async_session
    alerts_module.async_session = session_factory

    async with session_factory() as session:
        yield session

    alerts_module.async_session = original
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed_alert(
    db: AsyncSession,
    *,
    rule_id: str,
    severity: str = "warning",
    message: str = "test",
    state: str = "active",
    suppressed: bool = False,
    target_type: str = "system",
    target_id: int | None = None,
    created_at: datetime | None = None,
    acknowledged_at: datetime | None = None,
    resolved_at: datetime | None = None,
    resolution_source: str | None = None,
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
        acknowledged_at=acknowledged_at,
        resolved_at=resolved_at,
        resolution_source=resolution_source,
    )
    db.add(alert)
    await db.flush()
    return alert


async def _seed_sample_set(db: AsyncSession) -> dict[str, Alert]:
    """Seed a mix of rows used by several list tests."""
    now = _now()
    alerts: dict[str, Alert] = {}
    alerts["cpu"] = await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="CPU sustained high",
        created_at=now - timedelta(minutes=5),
    )
    alerts["unknown"] = await _seed_alert(
        db,
        rule_id="unknown_device:aa:bb:cc:dd:ee:ff",
        severity="info",
        message="Unknown device seen",
        created_at=now - timedelta(minutes=4),
    )
    alerts["service"] = await _seed_alert(
        db,
        rule_id="service_down",
        severity="critical",
        message="plex down",
        created_at=now - timedelta(minutes=3),
    )
    alerts["resolved"] = await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="old resolved",
        state="resolved",
        resolved_at=now - timedelta(minutes=2),
        resolution_source="auto",
        created_at=now - timedelta(minutes=2),
    )
    alerts["suppressed"] = await _seed_alert(
        db,
        rule_id="disk_high",
        severity="warning",
        message="muted disk",
        suppressed=True,
        created_at=now - timedelta(minutes=1),
    )
    await db.commit()
    return alerts


# ── (a) default list + 30-day clamp ─────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts_default_and_clamps_since(db_and_override):
    db = db_and_override
    now = _now()
    # Seed: one recent, one clamp-excluded (>30d old)
    await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="recent",
        created_at=now - timedelta(days=2),
    )
    await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="ancient",
        created_at=now - timedelta(days=60),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # No filters at all: both default include_suppressed=false and the
        # 30-day clamp should filter out the ancient row.
        resp_default = await client.get("/alerts")
        # Explicit since way in the past — should be clamped to 30 days ago,
        # so it STILL excludes the ancient row.
        old_since = (now - timedelta(days=365)).isoformat()
        resp_clamped = await client.get(f"/alerts?since={old_since}")

    assert resp_default.status_code == 200
    body_default = resp_default.json()
    messages = [a["message"] for a in body_default["items"]]
    assert "recent" in messages
    assert "ancient" not in messages
    assert body_default["total"] == 1

    assert resp_clamped.status_code == 200
    body_clamped = resp_clamped.json()
    clamped_messages = [a["message"] for a in body_clamped["items"]]
    assert "recent" in clamped_messages
    assert "ancient" not in clamped_messages
    assert body_clamped["total"] == 1


# ── (b) severity filter ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts_severity_filter(db_and_override):
    db = db_and_override
    await _seed_sample_set(db)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/alerts?severity=warning")

    assert resp.status_code == 200
    items = resp.json()["items"]
    # suppressed warning should be hidden by default; resolved warning remains.
    assert {i["message"] for i in items} == {"CPU sustained high", "old resolved"}
    assert all(i["severity"] == "warning" for i in items)


# ── (c) state filter ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts_state_filter(db_and_override):
    db = db_and_override
    await _seed_sample_set(db)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/alerts?state=resolved")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["message"] == "old resolved"
    assert items[0]["state"] == "resolved"


# ── (d) rule_id exact + prefix match ────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts_rule_id_exact_and_prefix(db_and_override):
    db = db_and_override
    await _seed_sample_set(db)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Exact rule_id match: returns active + resolved pi_cpu_high rows,
        # but not unknown_device:… .
        exact = await client.get("/alerts?rule_id=pi_cpu_high")
        # Prefix match: "unknown_device" should match
        # "unknown_device:aa:bb:cc:dd:ee:ff" via rule_id LIKE.
        prefix = await client.get("/alerts?rule_id=unknown_device")

    assert exact.status_code == 200
    exact_items = exact.json()["items"]
    messages = {i["message"] for i in exact_items}
    assert messages == {"CPU sustained high", "old resolved"}
    assert all(i["rule_id"] == "pi_cpu_high" for i in exact_items)

    assert prefix.status_code == 200
    prefix_items = prefix.json()["items"]
    assert len(prefix_items) == 1
    assert prefix_items[0]["rule_id"] == "unknown_device:aa:bb:cc:dd:ee:ff"
    assert prefix_items[0]["message"] == "Unknown device seen"


# ── (e) since/until bounds ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts_since_until_bounds(db_and_override):
    db = db_and_override
    now = _now()
    await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="t-10",
        created_at=now - timedelta(minutes=10),
    )
    await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="t-5",
        created_at=now - timedelta(minutes=5),
    )
    await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="t-1",
        created_at=now - timedelta(minutes=1),
    )
    await db.commit()

    since = (now - timedelta(minutes=7)).isoformat()
    until = (now - timedelta(minutes=2)).isoformat()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/alerts?since={since}&until={until}")

    assert resp.status_code == 200
    items = resp.json()["items"]
    messages = [i["message"] for i in items]
    assert messages == ["t-5"]


# ── (f) include_suppressed ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts_suppressed_toggle(db_and_override):
    db = db_and_override
    await _seed_sample_set(db)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        default_resp = await client.get("/alerts")
        included_resp = await client.get("/alerts?include_suppressed=true")

    default_items = default_resp.json()["items"]
    included_items = included_resp.json()["items"]

    default_messages = {i["message"] for i in default_items}
    included_messages = {i["message"] for i in included_items}

    assert "muted disk" not in default_messages
    assert "muted disk" in included_messages
    # Default hides one row (suppressed), included sees one more.
    assert len(included_items) == len(default_items) + 1


# ── (g) pagination: limit/offset with correct total ─────────────────────

@pytest.mark.asyncio
async def test_list_alerts_pagination(db_and_override):
    db = db_and_override
    now = _now()
    # Seed 5 visible (non-suppressed) warning rows.
    for i in range(5):
        await _seed_alert(
            db,
            rule_id="pi_cpu_high",
            severity="warning",
            message=f"row-{i}",
            created_at=now - timedelta(minutes=5 - i),
        )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        page1 = await client.get("/alerts?limit=2&offset=0")
        page2 = await client.get("/alerts?limit=2&offset=2")
        page3 = await client.get("/alerts?limit=2&offset=4")

    for resp in (page1, page2, page3):
        assert resp.status_code == 200
        assert resp.json()["total"] == 5

    p1 = page1.json()
    p2 = page2.json()
    p3 = page3.json()
    assert len(p1["items"]) == 2
    assert len(p2["items"]) == 2
    assert len(p3["items"]) == 1
    assert p1["limit"] == 2
    assert p1["offset"] == 0
    assert p3["offset"] == 4

    # Items are ordered by created_at desc: row-4 (newest) first.
    assert [i["message"] for i in p1["items"]] == ["row-4", "row-3"]
    assert [i["message"] for i in p2["items"]] == ["row-2", "row-1"]
    assert [i["message"] for i in p3["items"]] == ["row-0"]


# ── (h) acknowledge active → acknowledged ───────────────────────────────

@pytest.mark.asyncio
async def test_acknowledge_active_alert(db_and_override):
    db = db_and_override
    alert = await _seed_alert(
        db, rule_id="pi_cpu_high", severity="warning", message="m"
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/alerts/{alert.id}/acknowledge")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == alert.id
    assert body["state"] == "acknowledged"
    assert body["acknowledged_at"] is not None


# ── (i) acknowledge already acknowledged is idempotent ──────────────────

@pytest.mark.asyncio
async def test_acknowledge_already_acknowledged_is_idempotent(db_and_override):
    db = db_and_override
    prev_ack = _now() - timedelta(minutes=3)
    alert = await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="m",
        state="acknowledged",
        acknowledged_at=prev_ack,
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/alerts/{alert.id}/acknowledge")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == alert.id
    assert body["state"] == "acknowledged"
    assert body["acknowledged_at"] is not None


# ── (j) acknowledging a resolved alert returns 409 ──────────────────────

@pytest.mark.asyncio
async def test_acknowledge_resolved_alert_conflict(db_and_override):
    db = db_and_override
    alert = await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="already done",
        state="resolved",
        resolved_at=_now(),
        resolution_source="auto",
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/alerts/{alert.id}/acknowledge")

    assert resp.status_code == 409


# ── (k) resolve active → resolved (manual) ──────────────────────────────

@pytest.mark.asyncio
async def test_resolve_active_alert(db_and_override):
    db = db_and_override
    alert = await _seed_alert(
        db, rule_id="pi_cpu_high", severity="warning", message="m"
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/alerts/{alert.id}/resolve")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == alert.id
    assert body["state"] == "resolved"
    assert body["resolved_at"] is not None
    assert body["resolution_source"] == "manual"


# ── (l) resolve an acknowledged alert → resolved (manual) ───────────────

@pytest.mark.asyncio
async def test_resolve_acknowledged_alert(db_and_override):
    db = db_and_override
    alert = await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="m",
        state="acknowledged",
        acknowledged_at=_now() - timedelta(minutes=1),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/alerts/{alert.id}/resolve")

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "resolved"
    assert body["resolved_at"] is not None
    assert body["resolution_source"] == "manual"


# ── (m) resolving an already-resolved alert → 409 ───────────────────────

@pytest.mark.asyncio
async def test_resolve_already_resolved_conflict(db_and_override):
    db = db_and_override
    alert = await _seed_alert(
        db,
        rule_id="pi_cpu_high",
        severity="warning",
        message="already resolved",
        state="resolved",
        resolved_at=_now(),
        resolution_source="auto",
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/alerts/{alert.id}/resolve")

    assert resp.status_code == 409


# ── (n) unknown id on both endpoints → 404 ──────────────────────────────

@pytest.mark.asyncio
async def test_acknowledge_and_resolve_unknown_id(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        ack_resp = await client.post("/alerts/99999/acknowledge")
        resolve_resp = await client.post("/alerts/99999/resolve")

    assert ack_resp.status_code == 404
    assert resolve_resp.status_code == 404


# ── (o) invalid severity query value → 400 ──────────────────────────────

@pytest.mark.asyncio
async def test_list_alerts_invalid_severity(db_and_override):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/alerts?severity=bogus")

    assert resp.status_code == 400
