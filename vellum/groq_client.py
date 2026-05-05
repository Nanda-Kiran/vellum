"""Groq client wrapper for streaming, JSON mode, and response caching."""

from __future__ import annotations

from typing import Any

from groq import AsyncGroq

from vellum.settings import VellumSettings


class GroqClient:
    """Facade around Groq API access for all model calls."""

    def __init__(self, settings: VellumSettings) -> None:
        """Initialize Groq SDK client and in-memory cache."""
        self._settings = settings
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._cache: dict[str, dict[str, Any]] = {}

    async def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-shaped response from a Groq chat model."""
        raise NotImplementedError("TODO: Implement Groq JSON-mode chat call.")

    async def chat_stream(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Stream a model response and return the aggregated text."""
        raise NotImplementedError("TODO: Implement Groq streaming chat call.")

