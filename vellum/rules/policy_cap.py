"""Tier-0 expense policy cap checker."""

from __future__ import annotations

from vellum.contracts import Finding, Transaction


async def check_policy_caps(transactions: list[Transaction], cap_cents: int) -> list[Finding]:
    """Flag transactions that exceed configured expense caps."""
    _ = transactions
    _ = cap_cents
    raise NotImplementedError("TODO: Implement policy cap checks.")

