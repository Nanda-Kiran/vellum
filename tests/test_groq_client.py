"""Unit tests for Groq client wrapper behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import vellum.groq_client as groq_client


class _FakeStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> "_FakeStream":
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(outcomes))


class _RateLimitError(Exception):
    pass


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(groq_client, "_CACHE", {})
    monkeypatch.setattr(groq_client, "_CLIENT", None)


@pytest.mark.asyncio
async def test_call_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="cached text"))]
    )
    fake_client = _FakeClient([response])
    monkeypatch.setattr(groq_client, "_CLIENT", fake_client)

    messages = [{"role": "user", "content": "hello"}]
    first = await groq_client.call("fast", messages)
    second = await groq_client.call("fast", messages)

    assert first == "cached text"
    assert second == "cached text"
    assert len(fake_client.chat.completions.calls) == 1


@pytest.mark.asyncio
async def test_call_retries_on_transient_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    fake_client = _FakeClient([_RateLimitError("slow down"), _RateLimitError("still limited"), response])
    monkeypatch.setattr(groq_client, "_CLIENT", fake_client)

    sleeps: list[int] = []

    async def _fake_sleep(delay: int) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(groq_client.asyncio, "sleep", _fake_sleep)

    result = await groq_client.call("smart", [{"role": "user", "content": "retry"}], cacheable=False)

    assert result == "ok"
    assert len(fake_client.chat.completions.calls) == 3
    assert sleeps == [1, 2]


@pytest.mark.asyncio
async def test_call_enables_json_mode_and_schema_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict":"approve"}'))]
    )
    fake_client = _FakeClient([response])
    monkeypatch.setattr(groq_client, "_CLIENT", fake_client)

    schema = '{"type":"object","properties":{"verdict":{"type":"string"}}}'
    messages = [{"role": "system", "content": "You are strict."}, {"role": "user", "content": "Decide"}]
    result = await groq_client.call("fast", messages, schema=schema, cacheable=False)

    sent = fake_client.chat.completions.calls[0]
    assert result == {"verdict": "approve"}
    assert sent["response_format"] == {"type": "json_object"}
    assert "Return JSON matching schema" in sent["messages"][0]["content"]
    assert sent["messages"][0]["role"] == "system"
    assert messages[0]["content"] == "You are strict."


@pytest.mark.asyncio
async def test_call_stream_returns_token_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = _FakeStream(
        [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hel"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"))]),
        ]
    )
    fake_client = _FakeClient([stream])
    monkeypatch.setattr(groq_client, "_CLIENT", fake_client)

    token_gen = await groq_client.call(
        "fast",
        [{"role": "user", "content": "stream please"}],
        stream=True,
    )
    collected = [token async for token in token_gen]

    assert collected == ["hel", "lo"]
