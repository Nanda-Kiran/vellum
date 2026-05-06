"""FastAPI entrypoint wiring routers, logging, and background scheduler."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from vellum.api.audit import router as audit_router
from vellum.api.findings import router as findings_router
from vellum.integrations.slack_app import build_slack_app, start_socket_mode
from vellum.logging_setup import configure_logging, get_logger
from vellum.scheduler import build_scheduler
from vellum.settings import get_settings

configure_logging()
logger = get_logger(__name__)
scheduler = build_scheduler()
settings = get_settings()
slack_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background services and cleanly shut them down."""
    _ = app
    global slack_task
    if not scheduler.running:
        scheduler.start()
        logger.info("scheduler.started")
    if settings.slack_bot_token and settings.slack_app_token and slack_task is None:
        slack_app = build_slack_app(settings)
        slack_task = asyncio.create_task(start_socket_mode(slack_app, settings))
        logger.info("slack.socket_mode.started")
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("scheduler.stopped")
        if slack_task is not None:
            slack_task.cancel()
            try:
                await slack_task
            except asyncio.CancelledError:
                pass
            finally:
                slack_task = None
            logger.info("slack.socket_mode.stopped")


app = FastAPI(title="Vellum", version="0.1.0", lifespan=lifespan)
app.include_router(findings_router)
app.include_router(audit_router)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Return a lightweight readiness response."""
    return {"status": "ok"}

