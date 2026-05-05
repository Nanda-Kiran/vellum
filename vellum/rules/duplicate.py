"""Tier-0 duplicate payment detector."""

from __future__ import annotations

from vellum.contracts import Finding, Transaction


async def detect_duplicate_payments(transactions: list[Transaction]) -> list[Finding]:
    """Detect duplicate Stripe or bank payment transactions."""
    _ = transactions
    raise NotImplementedError("TODO: Implement duplicate payment detection.")

