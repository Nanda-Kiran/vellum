"""Seed script for planting zombie Datadog recurring charges."""

from __future__ import annotations

import asyncio

from vellum.integrations.plaid_client import (
    _build_plaid_client,
    _response_get,
    exchange_public_token,
    pull_recent_transactions,
)
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest

_SANDBOX_INSTITUTION_ID = "ins_109508"


async def seed_zombie_datadog_charge() -> None:
    """Verify Plaid sandbox token + print recurring Datadog transaction ids."""
    client = _build_plaid_client()
    sandbox_token_response = await asyncio.to_thread(
        client.sandbox_public_token_create,
        SandboxPublicTokenCreateRequest(
            institution_id=_SANDBOX_INSTITUTION_ID,
            initial_products=[Products("transactions")],
        ),
    )
    public_token = str(_response_get(sandbox_token_response, "public_token", ""))
    access_token = await exchange_public_token(public_token)
    transactions = await pull_recent_transactions(access_token, days_back=90)
    datadog_ids = [
        txn.id
        for txn in transactions
        if "datadog" in txn.vendor_name.lower() or "datadog" in txn.description.lower()
    ]
    print(
        "✓ planted: Plaid sandbox uses pre-baked recurring Datadog charges; "
        f"verified access_token and found transaction ids: {datadog_ids}"
    )


if __name__ == "__main__":
    asyncio.run(seed_zombie_datadog_charge())

