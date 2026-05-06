"""Slack streaming helper for live typing effects in DMs.

Example supervisor usage for conversational DM replies:

```python
from vellum.integrations.slack_stream import stream_to_slack

async def handle_dm_reply(channel: str, token_stream):
    message_ts = await stream_to_slack(
        channel=channel,
        generator=token_stream,
        initial_text="Vellum is investigating..."
    )
    return message_ts
```
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from slack_sdk.web.async_client import AsyncWebClient

from vellum.settings import get_settings

_UPDATE_INTERVAL_SECONDS = 0.3
_MIN_SLACK_UPDATE_SECONDS = 1.0


async def stream_to_slack(
    channel: str,
    generator: AsyncIterator[str],
    initial_text: str = "thinking...",
) -> str:
    """Post and incrementally update a Slack message from streamed tokens."""
    settings = get_settings()
    client = AsyncWebClient(token=settings.slack_bot_token)

    posted = await client.chat_postMessage(channel=channel, text=initial_text)
    message_ts = str(posted["ts"])

    accumulated_chunks: list[str] = []
    done = asyncio.Event()
    producer_error: Exception | None = None

    async def _consume_tokens() -> None:
        nonlocal producer_error
        try:
            async for token in generator:
                accumulated_chunks.append(token)
        except Exception as exc:  # pragma: no cover - bubbles to caller.
            producer_error = exc
        finally:
            done.set()

    producer_task = asyncio.create_task(_consume_tokens())

    last_sent_text = initial_text
    last_update_at = 0.0

    while not done.is_set():
        await asyncio.sleep(_UPDATE_INTERVAL_SECONDS)
        current_text = "".join(accumulated_chunks).strip() or initial_text
        if current_text == last_sent_text:
            continue

        now = time.monotonic()
        if now - last_update_at < _MIN_SLACK_UPDATE_SECONDS:
            continue
        await client.chat_update(channel=channel, ts=message_ts, text=current_text)
        last_sent_text = current_text
        last_update_at = now

    await producer_task
    if producer_error is not None:
        raise producer_error

    final_text = "".join(accumulated_chunks).strip() or initial_text
    if final_text != last_sent_text:
        await client.chat_update(channel=channel, ts=message_ts, text=final_text)

    return message_ts
