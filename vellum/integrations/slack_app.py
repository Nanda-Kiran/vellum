"""Slack Bolt Socket Mode app wiring."""

from __future__ import annotations

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler

from vellum.settings import VellumSettings


def build_slack_app(settings: VellumSettings) -> AsyncApp:
    """Create a Slack Bolt async app configured for Socket Mode."""
    return AsyncApp(token=settings.slack_bot_token)


async def start_socket_mode(app: AsyncApp, settings: VellumSettings) -> None:
    """Start the Slack Socket Mode handler."""
    handler = AsyncSocketModeHandler(app, settings.slack_app_token)
    await handler.start_async()

