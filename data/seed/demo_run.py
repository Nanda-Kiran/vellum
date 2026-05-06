"""One-command live demo runner for seeding integrations and posting Slack alerts."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from data.seed.gmail_seed import seed_vendor_fraud_email
from data.seed.plaid_seed import seed_zombie_datadog_charge
from data.seed.sheets_seed import seed_policy_violating_dinner
from data.seed.stripe_seed import seed_duplicate_acme_charge
from vellum.scheduler import ingestion_tick
from vellum.settings import get_settings


def _remove_sqlite_sidecars(db_path: Path) -> None:
    """Remove SQLite db + WAL sidecars to force a fresh demo ledger."""
    targets = [
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
    ]
    for target in targets:
        if target.exists():
            target.unlink()


async def run_demo(reset_ledger: bool) -> None:
    """Seed all integrations, then trigger one orchestration cycle."""
    settings = get_settings()
    db_path = Path(settings.vellum_db_path)

    print("=== Vellum Demo Runner ===")
    print(f"Ledger DB: {db_path}")
    if reset_ledger:
        _remove_sqlite_sidecars(db_path)
        print("Reset ledger database for fresh Slack postings.")

    print("\n[1/5] Seeding Stripe duplicate charges...")
    await seed_duplicate_acme_charge()

    print("\n[2/5] Seeding Plaid recurring charge context...")
    await seed_zombie_datadog_charge()

    print("\n[3/5] Seeding Google Sheets policy violation...")
    await seed_policy_violating_dinner()

    print("\n[4/5] Seeding Gmail fraud draft scenario...")
    try:
        await seed_vendor_fraud_email()
    except Exception as exc:
        print(f"Skipped Gmail seed: {exc}")
        print(
            "Fix: regenerate your Google OAuth token with gmail.compose scope, "
            "then rerun this demo command."
        )

    print("\n[5/5] Running ingestion tick (posts new findings to Slack)...")
    await ingestion_tick()

    print("\nDemo run complete.")
    print("If Gmail fraud alerts do not appear yet, send the drafted fraud email and rerun this script.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed all demo integrations and trigger Slack notifications."
    )
    parser.add_argument(
        "--reset-ledger",
        action="store_true",
        help="Delete local SQLite ledger DB before seeding to force fresh Slack posts.",
    )
    args = parser.parse_args()
    asyncio.run(run_demo(reset_ledger=args.reset_ledger))


if __name__ == "__main__":
    main()
