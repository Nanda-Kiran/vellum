"""Reporting agent for Slack summaries and audit pack composition."""

from __future__ import annotations

import json
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from vellum.contracts import Finding
from vellum.groq_client import call
from vellum.ledger import LedgerStore
from vellum.logging_setup import get_logger
from vellum.settings import get_settings

logger = get_logger(__name__)


class AuditPack(BaseModel):
    """Structured audit-pack payload for downstream doc generation and APIs."""

    period: str
    generated_at: datetime
    finding_count: int
    finding_ids: list[str] = Field(default_factory=list)
    total_revenue_saved_cents: int = 0
    business_impact_summary: str = ""
    executive_summary: str
    findings: list[dict[str, Any]] = Field(default_factory=list)


def _period_window(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if period == "last_30_days":
        return now - timedelta(days=30), now
    if len(period) == 7 and period[4] == "-":
        year = int(period[:4])
        month = int(period[5:7])
        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)
        return start, end
    return now - timedelta(days=30), now


async def _load_findings_for_period(period: str, ledger_store: LedgerStore | None) -> list[Finding]:
    settings = get_settings()
    store = ledger_store or LedgerStore(settings.vellum_db_path)
    try:
        entries = await store.list_entries()
    except NotImplementedError:
        logger.info("reporting.ledger_not_implemented")
        return []
    start, end = _period_window(period)
    findings: list[Finding] = []
    for entry in entries:
        created = entry.finding.created_at
        if start <= created < end:
            findings.append(entry.finding)
    return findings


def _coerce_cents(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(Decimal(str(value)))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(Decimal(text))
        except Exception:
            return None
    return None


def _extract_revenue_saved_cents(finding: Finding) -> int:
    total = 0
    evidence_keys = ("revenue_saved_cents", "estimated_savings_cents", "amount_saved_cents", "savings_cents")
    target_keys = ("revenue_saved_cents", "estimated_savings_cents", "amount_cents", "refund_cents")
    for evidence_item in finding.evidence:
        if not isinstance(evidence_item, dict):
            continue
        for key in evidence_keys:
            amount = _coerce_cents(evidence_item.get(key))
            if amount is not None and amount > 0:
                total += amount
    for action in finding.suggested_actions:
        for key in target_keys:
            amount = _coerce_cents(action.target.get(key))
            if amount is not None and amount > 0:
                total += amount
    return total


def _total_revenue_saved_cents(findings: list[Finding]) -> int:
    return sum(_extract_revenue_saved_cents(finding) for finding in findings)


def _build_business_impact_summary(findings: list[Finding], total_revenue_saved_cents: int) -> str:
    if not findings:
        return "No material business impact detected for this period."
    high_or_critical = sum(1 for finding in findings if finding.severity in {"high", "critical"})
    if total_revenue_saved_cents > 0:
        dollars = total_revenue_saved_cents / 100
        return (
            f"{len(findings)} findings identified, including {high_or_critical} high/critical risks, "
            f"with estimated recoverable value of ${dollars:,.2f}."
        )
    return (
        f"{len(findings)} findings identified, including {high_or_critical} high/critical risks, "
        "indicating operational and compliance exposure."
    )


async def run_reporting_agent(period: str, ledger_store: LedgerStore | None = None) -> dict[str, Any]:
    """Build a structured audit pack with one SMART-model executive summary."""
    findings = await _load_findings_for_period(period, ledger_store)
    summary = ""
    if findings:
        try:
            summary_response = await call(
                "smart",
                [
                    {
                        "role": "system",
                        "content": (
                            "Write a concise executive summary in exactly 3 paragraphs for finance leaders. "
                            "Cover risk themes, material items, and recommended controls."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "period": period,
                                "findings": [finding.model_dump(mode="json") for finding in findings],
                            }
                        ),
                    },
                ],
                cacheable=False,
                stream=False,
            )
            if isinstance(summary_response, str):
                summary = summary_response
        except Exception as exc:
            logger.info("reporting.summary_generation_failed", error=str(exc), finding_count=len(findings))

    total_revenue_saved_cents = _total_revenue_saved_cents(findings)
    pack = AuditPack(
        period=period,
        generated_at=datetime.now(UTC),
        finding_count=len(findings),
        finding_ids=[finding.id for finding in findings],
        total_revenue_saved_cents=total_revenue_saved_cents,
        business_impact_summary=_build_business_impact_summary(findings, total_revenue_saved_cents),
        executive_summary=summary,
        findings=[finding.model_dump(mode="json") for finding in findings],
    )
    return pack.model_dump(mode="json")

