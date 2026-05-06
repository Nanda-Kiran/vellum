"""Seed four live-demo issues and trigger Slack notifications."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path
from datetime import UTC, datetime, timedelta

from data.seed.gmail_seed import seed_vendor_fraud_email
from data.seed.plaid_seed import seed_zombie_datadog_charge
from data.seed.sheets_seed import seed_policy_violating_dinner
from data.seed.stripe_seed import seed_duplicate_acme_charge
from vellum.contracts import Finding, Transaction
from vellum.integrations.gmail_client import fetch_vendor_emails
from vellum.integrations.sheets_client import fetch_expense_rows
from vellum.integrations.slack_app import post_finding_card
from vellum.integrations.stripe_client import fetch_stripe_charges
from vellum.ledger import get_findings
from vellum.rules.domain_match import detect_domain_mismatch
from vellum.rules.duplicate import detect_duplicates
from vellum.rules.policy_cap import detect_policy_violations
from vellum.rules.zombie_saas import detect_zombie_saas
from vellum.settings import get_settings


_VENDOR_REGISTRY = {"Acme Corp": "acme.com"}


def _remove_sqlite_sidecars(db_path: Path) -> None:
    targets = [
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
    ]
    for target in targets:
        if target.exists():
            target.unlink()


async def _wait_for_enter(prompt: str) -> None:
    await asyncio.to_thread(input, prompt)


def _sheet_row_to_transaction(row: dict[str, object]) -> Transaction | None:
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


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return dict(value.to_dict_recursive())
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    return {}


def _fallback_datadog_transactions() -> list[Transaction]:
    now = datetime.now(UTC)
    return [
        Transaction(
            id=f"demo_plaid_datadog_{int((now - timedelta(days=31)).timestamp())}",
            source="manual",
            amount_cents=129_900,
            currency="USD",
            vendor_name="Datadog",
            vendor_normalized="datadog",
            description="Datadog monthly subscription",
            occurred_at=now - timedelta(days=31),
            category="software",
            raw={"seed": "demo_fallback"},
        ),
        Transaction(
            id=f"demo_plaid_datadog_{int(now.timestamp())}",
            source="manual",
            amount_cents=130_000,
            currency="USD",
            vendor_name="Datadog",
            vendor_normalized="datadog",
            description="Datadog monthly subscription",
            occurred_at=now,
            category="software",
            raw={"seed": "demo_fallback"},
        ),
    ]


async def _collect_targeted_demo_transactions() -> list[Transaction]:
    stripe_txns = await fetch_stripe_charges()
    stripe_demo: list[Transaction] = []
    for txn in stripe_txns:
        raw = _as_dict(txn.raw)
        metadata = _as_dict(raw.get("metadata"))
        if str(metadata.get("invoice", "")) == "INV-1042":
            stripe_demo.append(txn)
    stripe_demo.sort(key=lambda txn: txn.occurred_at, reverse=True)
    stripe_demo = stripe_demo[:2]

    sheet_rows = await fetch_expense_rows()
    sheet_txns = [txn for txn in (_sheet_row_to_transaction(row) for row in sheet_rows) if txn is not None]
    if sheet_txns:
        sheet_txns = [max(sheet_txns, key=lambda txn: txn.occurred_at)]

    # Plaid sandbox fixtures can vary; this fallback guarantees zombie-SaaS demo signal.
    datadog_fallback = _fallback_datadog_transactions()

    return [*stripe_demo, *sheet_txns, *datadog_fallback]


async def _post_new_findings(findings: list[Finding]) -> int:
    existing_ids = {finding.id for finding in await get_findings()}
    posted = 0
    for finding in findings:
        if finding.id in existing_ids:
            continue
        await post_finding_card(finding)
        posted += 1
    return posted


async def _run_targeted_detection_cycle(include_latest_gmail: bool) -> tuple[int, int]:
    transactions = await _collect_targeted_demo_transactions()
    findings: list[Finding] = []
    findings.extend(detect_duplicates(transactions))
    findings.extend(detect_zombie_saas(transactions, usage_signals={}))
    findings.extend(detect_policy_violations(transactions, {"meal_per_person_cap_cents": 15000}))

    if include_latest_gmail:
        emails = await fetch_vendor_emails()
        findings.extend(detect_domain_mismatch(emails, _VENDOR_REGISTRY))

    posted = await _post_new_findings(findings)
    return len(findings), posted


async def run_live_demo(*, reset_ledger: bool, wait_for_real_gmail: bool) -> None:
    settings = get_settings()
    db_path = Path(settings.vellum_db_path)

    print("=== Vellum Live Demo (4 Issues) ===")
    print("Targets: zombie SaaS, duplicate Stripe, vendor-domain mismatch, policy cap")
    print(f"Ledger DB: {db_path}")

    if reset_ledger:
        _remove_sqlite_sidecars(db_path)
        print("Reset ledger database for fresh Slack cards.")

    print("\n[1/6] Seed Plaid sandbox recurring Datadog context...")
    await seed_zombie_datadog_charge()

    print("\n[2/6] Seed Stripe duplicates ($4,200 x2, 3 days apart, Acme Corp)...")
    await seed_duplicate_acme_charge()

    print("\n[3/6] Seed Google Sheet policy-cap violation (meal, $890, 2 attendees)...")
    await seed_policy_violating_dinner()

    print("\n[4/6] Prepare Gmail fraud scenario helper draft...")
    try:
        await seed_vendor_fraud_email()
    except Exception as exc:
        print(f"Skipped Gmail draft helper: {exc}")
        print("Continuing demo. You can still send the real personal-Gmail email manually.")

    print("\n[5/6] Run targeted detection cycle (Stripe/Plaid/Sheets) and post to Slack...")
    findings_count, posted_count = await _run_targeted_detection_cycle(include_latest_gmail=False)
    print(f"Detected findings: {findings_count}; posted to Slack: {posted_count}")

    if wait_for_real_gmail:
        print("\nAction needed for domain-mismatch scenario:")
        print('Send a REAL email from your personal Gmail to the demo finance inbox with text like:')
        print('"Hi, Sarah from Acme, please update bank info to..."')
        print("Use a non-acme.com sender so vendor-domain mismatch can trigger.")
        await _wait_for_enter("\nPress Enter after sending that email...")
    else:
        print("\nSkipping wait for real Gmail email (--no-wait-for-gmail enabled).")

    print("\n[6/6] Run targeted cycle again to pick up latest Gmail message...")
    findings_count, posted_count = await _run_targeted_detection_cycle(include_latest_gmail=True)
    print(f"Detected findings: {findings_count}; posted to Slack: {posted_count}")

    print("\nDone.")
    print("- Slack cards include Why button for all findings.")
    print("- Policy cap findings include Approve/Reject buttons.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed four live-demo issues and trigger Slack notifications."
    )
    parser.add_argument(
        "--reset-ledger",
        action="store_true",
        help="Delete local SQLite ledger DB before run to force fresh Slack notifications.",
    )
    parser.add_argument(
        "--no-wait-for-gmail",
        action="store_true",
        help="Do not pause for manual personal-Gmail send before second ingestion.",
    )
    args = parser.parse_args()

    asyncio.run(
        run_live_demo(
            reset_ledger=args.reset_ledger,
            wait_for_real_gmail=not args.no_wait_for_gmail,
        )
    )


if __name__ == "__main__":
    main()
