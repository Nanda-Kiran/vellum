"""Audit pack API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from vellum.agents.reporting import run_reporting_agent
from vellum.integrations.docs_client import create_doc_from_template
from vellum.ledger import write_audit_pack

router = APIRouter(prefix="/audit", tags=["audit"])


def _format_usd_from_cents(cents: int) -> str:
    dollars = cents / 100
    return f"${dollars:,.2f}"


@router.post("/{period}")
async def build_audit_pack(period: str) -> dict[str, str]:
    """Create an audit pack for a period and return Google Doc URL."""
    pack = await run_reporting_agent(period)
    findings = pack.get("findings", [])
    findings_lines = [
        (
            f"- [{finding.get('severity', 'info')}] {finding.get('title', 'Untitled')} "
            f"({finding.get('id', 'unknown')})"
        )
        for finding in findings
    ]
    finding_section = "\n".join(findings_lines) if findings_lines else "- No findings for this period."
    total_revenue_saved_cents = int(pack.get("total_revenue_saved_cents", 0))
    total_revenue_saved = _format_usd_from_cents(total_revenue_saved_cents)
    business_impact_summary = str(pack.get("business_impact_summary", "")).strip()
    body_markdown = (
        f"# Vellum Audit Pack ({period})\n\n"
        "## Executive Summary\n"
        f"- Total revenue saved: {total_revenue_saved}\n\n"
        f"- Business impact: {business_impact_summary or 'No material impact summary available.'}\n\n"
        f"{pack.get('executive_summary', '').strip() or 'No summary generated.'}\n\n"
        "## Findings\n"
        f"{finding_section}\n"
    )
    gdoc_url = await create_doc_from_template(
        title=f"Vellum Audit Pack - {period}",
        body_markdown=body_markdown,
    )
    await write_audit_pack(
        period=period,
        gdoc_url=gdoc_url,
        finding_ids=[str(finding.get("id", "")) for finding in findings if finding.get("id")],
    )
    return {"gdoc_url": gdoc_url}

