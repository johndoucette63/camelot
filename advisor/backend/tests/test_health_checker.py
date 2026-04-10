"""Tests for health check logic (check_http, check_tcp)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.health_checker import check_http, check_tcp


@pytest.mark.asyncio
async def test_check_http_green():
    mock_resp = AsyncMock()
    mock_resp.status_code = 200

    with patch("app.services.health_checker.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        status, ms, err = await check_http("127.0.0.1", 8000, "/health", 2000)

    assert status == "green"
    assert ms is not None
    assert err is None


@pytest.mark.asyncio
async def test_check_http_yellow():
    """HTTP 200 but response time exceeds degraded threshold."""
    import time

    mock_resp = AsyncMock()
    mock_resp.status_code = 200

    original_monotonic = time.monotonic
    call_count = 0

    def slow_monotonic():
        nonlocal call_count
        call_count += 1
        base = original_monotonic()
        # Second call (after request) returns 3 seconds later
        if call_count >= 2:
            return base + 3.0
        return base

    with patch("app.services.health_checker.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with patch("app.services.health_checker.time.monotonic", side_effect=slow_monotonic):
            status, ms, err = await check_http("127.0.0.1", 8000, "/health", 2000)

    assert status == "yellow"
    assert ms is not None and ms > 2000
    assert err is None


@pytest.mark.asyncio
async def test_check_http_red_non200():
    mock_resp = AsyncMock()
    mock_resp.status_code = 503

    with patch("app.services.health_checker.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        status, ms, err = await check_http("127.0.0.1", 8000, "/health", 2000)

    assert status == "red"
    assert "503" in err


@pytest.mark.asyncio
async def test_check_http_red_timeout():
    import httpx

    with patch("app.services.health_checker.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.TimeoutException("timed out")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        status, ms, err = await check_http("127.0.0.1", 8000, "/health", 2000)

    assert status == "red"
    assert ms is None
    assert "timed out" in err


@pytest.mark.asyncio
async def test_check_tcp_green():
    mock_writer = AsyncMock()
    mock_writer.close = lambda: None
    mock_writer.wait_closed = AsyncMock()

    async def mock_open(*args, **kwargs):
        return (AsyncMock(), mock_writer)

    with patch("app.services.health_checker.asyncio.open_connection", side_effect=mock_open):
        status, ms, err = await check_tcp("127.0.0.1", 445)

    assert status == "green"
    assert err is None


@pytest.mark.asyncio
async def test_check_tcp_red():
    with patch("app.services.health_checker.asyncio.wait_for", side_effect=OSError("Connection refused")):
        status, ms, err = await check_tcp("127.0.0.1", 445)

    assert status == "red"
    assert ms is None
    assert "Connection refused" in err
