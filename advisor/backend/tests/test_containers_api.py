"""Tests for GET /containers endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_returns_container_state_when_healthy():
    app.state.container_state = {
        "running": [
            {"id": "abc123", "name": "plex", "image": "linuxserver/plex", "status": "running", "ports": {}, "uptime": "", "created": ""}
        ],
        "stopped": [],
        "refreshed_at": "2026-04-09T12:00:00Z",
        "socket_error": False,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/containers")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["running"]) == 1
    assert data["running"][0]["name"] == "plex"
    assert data["socket_error"] is False
    assert data["refreshed_at"] is not None


@pytest.mark.asyncio
async def test_returns_stale_data_with_socket_error_flag():
    app.state.container_state = {
        "running": [
            {"id": "abc123", "name": "plex", "image": "linuxserver/plex", "status": "running", "ports": {}, "uptime": "", "created": ""}
        ],
        "stopped": [],
        "refreshed_at": "2026-04-09T10:00:00Z",
        "socket_error": True,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/containers")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["running"]) == 1
    assert data["socket_error"] is True


@pytest.mark.asyncio
async def test_returns_empty_on_first_boot():
    app.state.container_state = {
        "running": [],
        "stopped": [],
        "refreshed_at": None,
        "socket_error": True,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/containers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] == []
    assert data["stopped"] == []
    assert data["refreshed_at"] is None
    assert data["socket_error"] is True
