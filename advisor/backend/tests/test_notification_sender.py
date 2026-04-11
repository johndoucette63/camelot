"""Tests for app.services.notification_sender (User Story 5).

Covers _meets_cutoff, deliver, and send_test — no network access.
httpx.AsyncClient is stubbed at the module level for every test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.alert import Alert
from app.models.notification_sink import NotificationSink
from app.services import notification_sender
from app.services.notification_sender import (
    _meets_cutoff,
    deliver,
    send_test,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def _make_client(behaviour):
    """Build a fake httpx.AsyncClient whose `post` runs ``behaviour``."""

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, **kwargs):
            return await behaviour(url, json)

    return _FakeClient


def _install_fake_httpx(monkeypatch, behaviour):
    monkeypatch.setattr(
        notification_sender.httpx, "AsyncClient", _make_client(behaviour)
    )


async def _insert_sink(
    db,
    *,
    name="ha",
    endpoint="http://ha.local/api/webhook/token",
    min_severity="warning",
    enabled=True,
) -> NotificationSink:
    sink = NotificationSink(
        type="home_assistant",
        name=name,
        enabled=enabled,
        endpoint=endpoint,
        min_severity=min_severity,
    )
    db.add(sink)
    await db.commit()
    await db.refresh(sink)
    return sink


async def _insert_alert(
    db,
    *,
    severity="warning",
    rule_id="disk_high",
    message="disk full",
) -> Alert:
    alert = Alert(
        rule_id=rule_id,
        target_type="device",
        target_id=1,
        severity=severity,
        message=message,
        state="active",
        source="rule",
        suppressed=False,
        created_at=_now(),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


# ── (a) _meets_cutoff behaviour ────────────────────────────────────────


def test_meets_cutoff_critical_sink_only_accepts_critical():
    assert _meets_cutoff("critical", "critical") is True
    assert _meets_cutoff("critical", "warning") is False
    assert _meets_cutoff("critical", "info") is False


def test_meets_cutoff_warning_sink_accepts_warning_and_critical():
    assert _meets_cutoff("warning", "critical") is True
    assert _meets_cutoff("warning", "warning") is True
    assert _meets_cutoff("warning", "info") is False


def test_meets_cutoff_info_sink_accepts_everything():
    assert _meets_cutoff("info", "critical") is True
    assert _meets_cutoff("info", "warning") is True
    assert _meets_cutoff("info", "info") is True


# ── (b) successful POST ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_successful_post(db, monkeypatch):
    await _insert_sink(db, min_severity="warning", enabled=True)
    alert = await _insert_alert(db, severity="warning")

    posts = []

    async def _ok(url, payload):
        posts.append((url, payload))
        return SimpleNamespace(status_code=200, text="")

    _install_fake_httpx(monkeypatch, _ok)

    attempted, succeeded = await deliver(db, alert)
    assert attempted == 1
    assert succeeded == 1
    assert len(posts) == 1
    _, payload = posts[0]
    assert payload["message"] == "disk full"
    assert payload["severity"] == "warning"
    assert payload["rule_id"] == "disk_high"


# ── (c) connection error swallowed ─────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_connection_error(db, monkeypatch, caplog):
    await _insert_sink(db, min_severity="warning", enabled=True)
    alert = await _insert_alert(db, severity="warning")

    async def _boom(url, payload):
        raise httpx.ConnectError("connection refused")

    _install_fake_httpx(monkeypatch, _boom)

    with caplog.at_level("WARNING", logger="app.services.notification_sender"):
        attempted, succeeded = await deliver(db, alert)

    assert attempted == 1
    assert succeeded == 0
    # The failure event is logged for observability.
    assert any(
        "rule_engine.ha.delivery_failed" in rec.message for rec in caplog.records
    )


# ── (d) severity cutoff filters sinks ──────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_severity_cutoff_filters_sinks(db, monkeypatch):
    # One sink at warning (should receive the warning alert),
    # one at critical (should NOT be attempted).
    await _insert_sink(
        db,
        name="ha-warning",
        endpoint="http://ha/api/webhook/w",
        min_severity="warning",
        enabled=True,
    )
    await _insert_sink(
        db,
        name="ha-critical",
        endpoint="http://ha/api/webhook/c",
        min_severity="critical",
        enabled=True,
    )
    alert = await _insert_alert(db, severity="warning")

    posted_urls = []

    async def _ok(url, payload):
        posted_urls.append(url)
        return SimpleNamespace(status_code=200, text="")

    _install_fake_httpx(monkeypatch, _ok)

    attempted, succeeded = await deliver(db, alert)
    assert attempted == 1
    assert succeeded == 1
    assert posted_urls == ["http://ha/api/webhook/w"]


# ── (e) send_test success/failure ──────────────────────────────────────


@pytest.mark.asyncio
async def test_send_test_success(db, monkeypatch):
    sink = await _insert_sink(db)

    async def _ok(url, payload):
        return SimpleNamespace(status_code=200, text="")

    _install_fake_httpx(monkeypatch, _ok)

    result = await send_test(sink)
    assert result["ok"] is True
    assert result["status_code"] == 200
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_send_test_connection_error(db, monkeypatch):
    sink = await _insert_sink(db)

    async def _boom(url, payload):
        raise httpx.ConnectError("refused")

    _install_fake_httpx(monkeypatch, _boom)

    result = await send_test(sink)
    assert result["ok"] is False
    assert "error" in result
    assert "refused" in result["error"]
