"""Background scheduling for periodic ingestion orchestration."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from vellum.logging_setup import get_logger

logger = get_logger(__name__)


def build_scheduler(ingestion_job: Callable[[], Awaitable[None]]) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(ingestion_job, "interval", seconds=90, id="ingestion_cycle")
    return scheduler


async def ingestion_tick() -> None:
    """Run a single scheduler-driven ingestion tick."""
    logger.info("scheduler.ingestion_tick", status="todo")
    await asyncio.sleep(0)

