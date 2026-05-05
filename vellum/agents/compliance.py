"""Compliance agent for policy and control validation."""

from __future__ import annotations

from vellum.contracts import Finding, Transaction


async def run_compliance_agent(transactions: list[Transaction]) -> list[Finding]:
    """Check activity against internal accounting and spend policies."""
    _ = transactions
    raise NotImplementedError("TODO: Implement compliance agent.")

