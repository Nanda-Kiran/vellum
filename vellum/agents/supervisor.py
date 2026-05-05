"""LangGraph supervisor that orchestrates specialist agents."""

from __future__ import annotations

from typing import Any


async def run_supervisor(state: dict[str, Any]) -> dict[str, Any]:
    """Route graph state between ingestion, forensics, and reporting agents."""
    _ = state
    raise NotImplementedError("TODO: Implement LangGraph supervisor flow.")

