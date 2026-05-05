"""Async Stripe integration wrapper."""

from __future__ import annotations

from vellum.contracts import Transaction


async def fetch_stripe_charges() -> list[Transaction]:
    """Fetch and normalize charge-like events from Stripe."""
    raise NotImplementedError("TODO: Implement Stripe charge ingestion.")

