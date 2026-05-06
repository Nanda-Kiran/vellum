"""Background scheduling for periodic ingestion orchestration."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from vellum.agents.supervisor import run_supervisor
from vellum.contracts import Transaction
from vellum.integrations.gmail_client import fetch_vendor_emails
from vellum.integrations.plaid_client import fetch_plaid_transactions
from vellum.integrations.sheets_client import fetch_expense_rows
from vellum.integrations.slack_app import post_finding_card
from vellum.integrations.stripe_client import fetch_stripe_charges
from vellum.ledger import get_findings
from vellum.logging_setup import get_logger
from vellum.rules.domain_match import detect_domain_mismatch

logger = get_logger(__name__)
_SCHEDULER = AsyncIOScheduler()
_VENDOR_REGISTRY = {"Acme Corp": "acme.com"}


def _sheet_row_to_transaction(row: dict[str, Any]) -> Transaction | None:
    amount_value = row.get("amount")
    description = str(row.get("description", "")).strip()
    if not description:
        return None
    try:
        amount_dollars = float(str(amount_value))
    except (TypeError, ValueError):
        return None

    date_raw = str(row.get("date", "")).strip()
    try:
        occurred_at = datetime.fromisoformat(date_raw).replace(tzinfo=UTC)
    except ValueError:
        occurred_at = datetime.now(UTC)

    row_payload = {
        "date": date_raw,
        "category": row.get("category"),
        "description": description,
        "amount": amount_value,
        "submitter": row.get("submitter"),
    }
    row_id = hashlib.sha256(repr(row_payload).encode("utf-8")).hexdigest()[:16]
    return Transaction(
        id=f"sheets_{row_id}",
        source="manual",
        amount_cents=int(amount_dollars * 100),
        currency="USD",
        vendor_name=str(row.get("submitter") or "Sheet Expense"),
        vendor_normalized=str(row.get("submitter") or "Sheet Expense"),
        description=description,
        occurred_at=occurred_at,
        category=str(row.get("category")) if row.get("category") else None,
        raw={"sheet_row": row_payload},
    )


def build_scheduler() -> AsyncIOScheduler:
    """Create and configure a single APScheduler instance."""
    if not _SCHEDULER.get_job("ingestion_cycle"):
        _SCHEDULER.add_job(ingestion_tick, "interval", seconds=90, id="ingestion_cycle")
    return _SCHEDULER


async def ingestion_tick() -> None:
    """Run one ingestion + detection + Slack alert cycle."""
    logger.info("scheduler.ingestion_tick.start")
    plaid_txns, stripe_charges, emails, expense_rows = await _gather_sources()
    sheet_txns = [txn for txn in (_sheet_row_to_transaction(row) for row in expense_rows) if txn is not None]
    seed_findings = detect_domain_mismatch(emails, _VENDOR_REGISTRY)

    new_txns = [*plaid_txns, *stripe_charges, *sheet_txns]
    if not new_txns and not seed_findings:
        logger.info("scheduler.ingestion_tick.no_data")
        return

    state = await run_supervisor(
        {
            "user_message": None,
            "new_txns": new_txns,
            "findings": seed_findings,
            "pending_actions": [],
            "final_response": None,
        }
    )
    findings = state.get("findings", [])
    if not findings:
        logger.info("scheduler.ingestion_tick.no_findings")
        return

    existing_ids = {finding.id for finding in await get_findings()}
    posted_count = 0
    for finding in findings:
        if finding.id in existing_ids:
            continue
        await post_finding_card(finding)
        posted_count += 1
    logger.info("scheduler.ingestion_tick.completed", findings=len(findings), posted=posted_count)


async def _gather_sources() -> tuple[list[Transaction], list[Transaction], list[dict], list[dict]]:
    plaid_task = fetch_plaid_transactions()
    stripe_task = fetch_stripe_charges()
    gmail_task = fetch_vendor_emails()
    sheets_task = fetch_expense_rows()
    plaid_txns, stripe_charges, emails, expense_rows = await asyncio.gather(
        plaid_task,
        stripe_task,
        gmail_task,
        sheets_task,
        return_exceptions=True,
    )

    def _as_list(value: Any) -> list[Any]:
        if isinstance(value, Exception):
            logger.info("scheduler.source_failed", error=str(value))
            return []
        return list(value)

    return (
        _as_list(plaid_txns),
        _as_list(stripe_charges),
        _as_list(emails),
        _as_list(expense_rows),
    )

