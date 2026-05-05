"""Async Plaid integration wrapper."""

from __future__ import annotations

from vellum.contracts import Transaction


async def fetch_plaid_transactions() -> list[Transaction]:
    """Fetch and normalize transactions from Plaid."""
    raise NotImplementedError("TODO: Implement Plaid transaction ingestion.")

