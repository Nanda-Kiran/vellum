"""Async Groq wrapper for model-tier routing, caching, and JSON mode.

Task-tier defaults used by :func:`pick_tier`:
- ``triage`` -> ``fast``
- ``routing`` -> ``fast``
- ``classification`` -> ``fast``
- ``extraction`` -> ``fast``
- ``reasoning`` -> ``smart``
- ``forensics`` -> ``smart``
- ``investigation`` -> ``smart``
- ``audit`` -> ``smart``
Any unknown task defaults to ``fast``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from typing import AsyncGenerator

try:
    from groq import AsyncGroq
except ImportError:  # pragma: no cover - surfaced at runtime if dependency missing.
    AsyncGroq = None  # type: ignore[assignment]

from vellum.settings import get_settings

FAST = "llama-3.1-8b-instant"
SMART = "llama-3.3-70b-versatile"

_TIER_BY_TASK = {
    "triage": "fast",
    "routing": "fast",
    "classification": "fast",
    "extraction": "fast",
    "reasoning": "smart",
    "forensics": "smart",
    "investigation": "smart",
    "audit": "smart",
}
_RETRY_DELAYS_SECONDS = (1, 2, 4)
_CACHE: dict[str, Any] = {}
_CLIENT: Any | None = None


def pick_tier(task: str) -> str:
    """Return ``fast`` or ``smart`` using task defaults from this module docstring."""
    return _TIER_BY_TASK.get(task.strip().lower(), "fast")


def _model_for_tier(tier: str) -> str:
    normalized = tier.strip().lower()
    if normalized == "fast":
        return FAST
    if normalized == "smart":
        return SMART
    raise ValueError("tier must be 'fast' or 'smart'")


def _get_client() -> Any:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    if AsyncGroq is None:
        raise RuntimeError("groq SDK is not installed")
    settings = get_settings()
    if not settings.groq_api_key:
        raise ValueError("Missing GROQ_API_KEY in settings")
    _CLIENT = AsyncGroq(api_key=settings.groq_api_key)
    return _CLIENT


def _cache_key(model: str, messages: list[dict[str, str]], schema: str | None) -> str:
    payload = json.dumps(
        {"model": model, "messages": messages, "schema": schema},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _prepare_messages(messages: list[dict[str, str]], schema: str | None) -> list[dict[str, str]]:
    prepared = [dict(message) for message in messages]
    if not schema:
        return prepared
    suffix = f"Return JSON matching schema: {schema}"
    for message in prepared:
        if message.get("role") == "system":
            content = message.get("content", "")
            message["content"] = f"{content}\n\n{suffix}" if content else suffix
            return prepared
    prepared.insert(0, {"role": "system", "content": suffix})
    return prepared


def _extract_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ValueError("Unexpected Groq response shape") from exc
    if content is None:
        return ""
    return str(content)


def _extract_stream_delta(chunk: Any) -> str:
    try:
        delta = chunk.choices[0].delta.content
    except (AttributeError, IndexError, KeyError, TypeError):
        return ""
    if delta is None:
        return ""
    return str(delta)


def _is_transient_error(exc: Exception) -> bool:
    message = str(exc).lower()
    # Quota exhaustion errors won't recover with retries in the same request.
    if "tokens per day" in message or "rate_limit_exceeded" in message:
        return False
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (status_code == 429 or status_code >= 500):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = exc.__class__.__name__.lower()
    return any(token in name for token in ("rate", "timeout", "connection", "temporary"))


async def call(
    tier: str,
    messages: list[dict[str, str]],
    schema: str | None = None,
    cacheable: bool = True,
    stream: bool = False,
) -> str | dict[str, Any] | AsyncGenerator[str, None]:
    """Call a Groq chat model with optional JSON mode, caching, retries, and streaming."""
    model = _model_for_tier(tier)
    key = _cache_key(model, messages, schema)
    if cacheable and not stream and key in _CACHE:
        return _CACHE[key]

    request_messages = _prepare_messages(messages, schema)
    request: dict[str, Any] = {
        "model": model,
        "messages": request_messages,
        "stream": stream,
    }
    if schema:
        request["response_format"] = {"type": "json_object"}

    client = _get_client()
    for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
        try:
            if stream:
                stream_response = await client.chat.completions.create(**request)

                async def token_generator() -> AsyncGenerator[str, None]:
                    async for chunk in stream_response:
                        token = _extract_stream_delta(chunk)
                        if token:
                            yield token

                return token_generator()

            response = await client.chat.completions.create(**request)
            text_content = _extract_content(response)
            result: str | dict[str, Any]
            if schema:
                result = json.loads(text_content)
            else:
                result = text_content
            if cacheable:
                _CACHE[key] = result
            return result
        except Exception as exc:
            if attempt >= len(_RETRY_DELAYS_SECONDS) or not _is_transient_error(exc):
                raise
            await asyncio.sleep(_RETRY_DELAYS_SECONDS[attempt])

    raise RuntimeError("Unreachable retry state")

