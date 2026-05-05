"""Tier-0 vendor email domain matcher."""

from __future__ import annotations

from vellum.contracts import Finding


async def detect_domain_mismatch(vendor_name: str, sender_email: str) -> list[Finding]:
    """Flag messages whose sender domain mismatches trusted vendor domains."""
    _ = vendor_name
    _ = sender_email
    raise NotImplementedError("TODO: Implement sender domain matching.")

