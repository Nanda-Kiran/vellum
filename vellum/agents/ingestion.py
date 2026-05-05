"""Ingestion agent for source collection and normalization."""

from __future__ import annotations

from vellum.contracts import Transaction


async def run_ingestion_agent() -> list[Transaction]:
    """Collect transactions from connected systems and normalize them."""
    raise NotImplementedError("TODO: Implement ingestion agent.")

