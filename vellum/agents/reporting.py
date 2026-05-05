"""Reporting agent for Slack summaries and audit pack composition."""

from __future__ import annotations

from vellum.contracts import Finding


async def run_reporting_agent(findings: list[Finding]) -> str:
    """Compile findings into a human-readable report artifact."""
    _ = findings
    raise NotImplementedError("TODO: Implement reporting agent.")

