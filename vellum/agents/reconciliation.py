"""Reconciliation agent for deterministic payment consistency checks."""

from __future__ import annotations

from vellum.contracts import Finding, Transaction


async def run_reconciliation_agent(transactions: list[Transaction]) -> list[Finding]:
    """Run reconciliation passes and output candidate findings."""
    _ = transactions
    raise NotImplementedError("TODO: Implement reconciliation agent.")

