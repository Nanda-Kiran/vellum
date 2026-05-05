"""FastAPI entrypoint wiring routers, logging, and background scheduler."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from vellum.api.audit import router as audit_router
from vellum.api.findings import router as findings_router
from vellum.logging_setup import configure_logging, get_logger
from vellum.scheduler import build_scheduler, ingestion_tick

configure_logging()
logger = get_logger(__name__)
scheduler = build_scheduler(ingestion_tick)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background services and cleanly shut them down."""
    _ = app
    if not scheduler.running:
        scheduler.start()
        logger.info("scheduler.started")
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("scheduler.stopped")


app = FastAPI(title="Vellum", version="0.1.0", lifespan=lifespan)
app.include_router(findings_router)
app.include_router(audit_router)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Return a lightweight readiness response."""
    return {"status": "ok"}

