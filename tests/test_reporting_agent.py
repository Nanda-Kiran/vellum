"""Tests for reporting-agent audit metrics."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vellum.agents.reporting import run_reporting_agent
from vellum.api.audit import _format_usd_from_cents
from vellum.contracts import Action, Finding, LedgerEntry


class _FakeLedgerStore:
    def __init__(self, entries: list[LedgerEntry]) -> None:
        self._entries = entries

    async def list_entries(self) -> list[LedgerEntry]:
        return self._entries


@pytest.mark.asyncio
async def test_run_reporting_agent_includes_total_revenue_saved_cents(monkeypatch: pytest.MonkeyPatch) -> None:
    """Revenue saved aggregates from evidence and action targets."""

    async def _fake_call(*args, **kwargs):  # noqa: ANN001, ANN002
        return "Summary"

    monkeypatch.setattr("vellum.agents.reporting.call", _fake_call)

    finding = Finding(
        id="find_revenue",
        agent="reporting",
        finding_type="recovered_revenue",
        severity="high",
        confidence=0.9,
        title="Recovered duplicate charge",
        summary="Recovered amount available.",
        evidence=[{"estimated_savings_cents": 12_500}],
        reasoning_trace="",
        suggested_actions=[
            Action(
                id="act_refund",
                action_type="request_clawback",
                target={"refund_cents": 25_00},
                requires_approval=True,
                status="pending",
            )
        ],
        created_at=datetime.now(UTC),
    )
    entry = LedgerEntry(finding=finding)
    result = await run_reporting_agent("last_30_days", ledger_store=_FakeLedgerStore([entry]))

    assert result["total_revenue_saved_cents"] == 15_000
    assert "estimated recoverable value of $150.00" in result["business_impact_summary"]


def test_format_usd_from_cents() -> None:
    """Audit API formats currency for the markdown summary."""
    assert _format_usd_from_cents(15000) == "$150.00"
