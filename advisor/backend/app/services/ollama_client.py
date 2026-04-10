"""Async streaming client for the local Ollama LLM.

Calls Ollama's native `/api/chat` endpoint and yields assistant token content
as each newline-delimited JSON frame arrives. Used by the chat router to
stream advisor replies back to the browser.

Ollama reference: https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-chat-completion
"""

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaUnreachableError(RuntimeError):
    """Raised when the Ollama backend cannot be reached or returns an error
    before any tokens have been produced."""


async def stream_chat(
    messages: list[dict],
    model: str | None = None,
) -> AsyncIterator[str]:
    """Stream assistant token content from Ollama's /api/chat endpoint.

    Yields text chunks as they arrive. The generator completes when Ollama
    signals `done: true`. Raises `OllamaUnreachableError` if the backend is
    unreachable or returns a non-2xx status before any tokens are yielded.
    """
    model = model or settings.ollama_model
    url = f"{settings.ollama_url.rstrip('/')}/api/chat"
    payload = {"model": model, "messages": messages, "stream": True}

    # Short connect/write/pool timeouts so an unreachable Ollama surfaces in
    # ~5s (SC-005). read=None lets long generations stream without aborting.
    timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise OllamaUnreachableError(
                        f"Ollama returned {response.status_code}: {body.decode(errors='replace')[:200]}"
                    )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        frame = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("ollama_bad_frame", extra={"line": line[:200]})
                        continue
                    if frame.get("done"):
                        return
                    msg = frame.get("message") or {}
                    content = msg.get("content")
                    if content:
                        yield content
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
        raise OllamaUnreachableError(f"Could not reach Ollama at {url}: {e}") from e
    except httpx.HTTPError as e:
        raise OllamaUnreachableError(f"Ollama HTTP error: {e}") from e
