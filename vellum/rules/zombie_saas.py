"""Tier-0 unused recurring SaaS charge detector."""

from __future__ import annotations

from vellum.contracts import Finding, Transaction


async def detect_zombie_saas(transactions: list[Transaction]) -> list[Finding]:
    """Identify recurring charges with no recent product usage signal."""
    _ = transactions
    raise NotImplementedError("TODO: Implement zombie SaaS detection.")

