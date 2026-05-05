"""Forensics agent for high-signal fraud pattern analysis."""

from __future__ import annotations

from vellum.contracts import Finding, Transaction


async def run_forensics_agent(transactions: list[Transaction]) -> list[Finding]:
    """Evaluate transaction and communication patterns for fraud indicators."""
    _ = transactions
    raise NotImplementedError("TODO: Implement forensics agent.")

