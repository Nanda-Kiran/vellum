"""Ingestion agent for source collection and normalization."""

from __future__ import annotations

import json

from vellum.contracts import Transaction
from vellum.groq_client import call
from vellum.integrations.plaid_client import fetch_plaid_transactions
from vellum.integrations.stripe_client import fetch_stripe_charges
from vellum.logging_setup import get_logger

logger = get_logger(__name__)


async def run_ingestion_agent(seed_transactions: list[Transaction] | None = None) -> list[Transaction]:
    """Collect transactions from connected systems and optionally enrich categories."""
    transactions: list[Transaction] = list(seed_transactions or [])

    for loader in (fetch_plaid_transactions, fetch_stripe_charges):
        try:
            transactions.extend(await loader())
        except NotImplementedError:
            logger.info("ingestion.source_not_implemented", source=loader.__name__)

    if not transactions:
        return []

    # Fast model pass for cheap per-transaction category refinement.
    schema = json.dumps(
        {
            "type": "object",
            "properties": {"category": {"type": "string"}},
            "required": ["category"],
        }
    )
    for txn in transactions:
        try:
            response = await call(
                "fast",
                [
                    {
                        "role": "system",
                        "content": "Classify the transaction into a short lowercase expense category.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Vendor: {txn.vendor_name}\n"
                            f"Description: {txn.description}\n"
                            f"Current category: {txn.category or 'unknown'}"
                        ),
                    },
                ],
                schema=schema,
                cacheable=True,
                stream=False,
            )
            if isinstance(response, dict):
                category = str(response.get("category", "")).strip().lower()
                if category:
                    txn.category = category
        except Exception:
            logger.info("ingestion.fast_category_failed", transaction_id=txn.id)

    return transactions

