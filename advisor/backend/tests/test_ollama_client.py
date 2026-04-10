"""Tests for the Ollama streaming client.

The only external boundary here is the HTTP transport to Ollama, so we use
httpx.MockTransport to serve a canned ndjson response body and a connect
error for the sad-path test.
"""

import json

import httpx
import pytest

from app.services import ollama_client


def _build_ndjson_body(contents: list[str]) -> bytes:
    """Fake an Ollama /api/chat streaming response body."""
    lines: list[str] = []
    for c in contents:
        lines.append(json.dumps({"message": {"role": "assistant", "content": c}, "done": False}))
    lines.append(json.dumps({"done": True, "eval_count": len(contents)}))
    return ("\n".join(lines) + "\n").encode("utf-8")


@pytest.mark.asyncio
async def test_stream_chat_yields_content_from_ndjson_chunks(monkeypatch):
    body = _build_ndjson_body(["Hello", " ", "world"])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["messages"][-1]["role"] == "user"
        return httpx.Response(200, content=body)

    mock_transport = httpx.MockTransport(handler)

    # Patch AsyncClient so our client uses the MockTransport.
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(ollama_client.httpx, "AsyncClient", patched_async_client)

    tokens = []
    async for chunk in ollama_client.stream_chat(
        [{"role": "user", "content": "Hi"}], model="test"
    ):
        tokens.append(chunk)
    assert tokens == ["Hello", " ", "world"]


@pytest.mark.asyncio
async def test_stream_chat_raises_ollama_unreachable_on_connect_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    mock_transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(ollama_client.httpx, "AsyncClient", patched_async_client)

    with pytest.raises(ollama_client.OllamaUnreachableError):
        async for _ in ollama_client.stream_chat(
            [{"role": "user", "content": "Hi"}], model="test"
        ):
            pass


@pytest.mark.asyncio
async def test_stream_chat_raises_on_http_error_status(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"internal error")

    mock_transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(ollama_client.httpx, "AsyncClient", patched_async_client)

    with pytest.raises(ollama_client.OllamaUnreachableError):
        async for _ in ollama_client.stream_chat(
            [{"role": "user", "content": "Hi"}], model="test"
        ):
            pass
