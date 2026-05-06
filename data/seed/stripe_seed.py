"""Seed script for planting duplicate Stripe charges."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import stripe

from vellum.settings import get_settings

_ACME_EMAIL = "ap@acmecorp.test"
_ACME_NAME = "Acme Corp"
_INVOICE_ID = "INV-1042"
_AMOUNT_CENTS = 420000


def _to_dict(payload: object) -> dict:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "to_dict_recursive"):
        return dict(payload.to_dict_recursive())
    raw_data = getattr(payload, "_data", None)
    if isinstance(raw_data, dict):
        return dict(raw_data)
    return dict(payload)


async def _find_or_create_customer() -> str:
    settings = get_settings()
    stripe.api_key = settings.stripe_api_key
    listed = await asyncio.to_thread(stripe.Customer.list, email=_ACME_EMAIL, limit=1)
    listed_dict = _to_dict(listed)
    existing = listed_dict.get("data", [])
    if existing:
        existing_customer = _to_dict(existing[0])
        customer_id = str(existing_customer.get("id", ""))
        if customer_id and not existing_customer.get("default_source"):
            await asyncio.to_thread(stripe.Customer.create_source, customer_id, source="tok_visa")
        return customer_id
    created = await asyncio.to_thread(
        stripe.Customer.create,
        name=_ACME_NAME,
        email=_ACME_EMAIL,
        source="tok_visa",
        metadata={"seed": "vellum_demo"},
    )
    created_dict = _to_dict(created)
    return str(created_dict.get("id", ""))


async def _create_charge(customer_id: str, intended_offset_days: int) -> str:
    intended_date = (datetime.now(UTC) + timedelta(days=intended_offset_days)).date().isoformat()
    charge = await asyncio.to_thread(
        stripe.Charge.create,
        customer=customer_id,
        amount=_AMOUNT_CENTS,
        currency="usd",
        description=f"{_ACME_NAME} invoice {_INVOICE_ID}",
        metadata={
            "invoice": _INVOICE_ID,
            "intended_charge_date": intended_date,
            "seed": "vellum_duplicate_demo",
        },
    )
    charge_dict = _to_dict(charge)
    return str(charge_dict.get("id", ""))


async def seed_duplicate_acme_charge() -> None:
    """Create duplicate Acme Stripe charges in test mode."""
    settings = get_settings()
    if not settings.stripe_api_key:
        raise ValueError("Missing STRIPE_API_KEY for stripe seeding")

    customer_id = await _find_or_create_customer()
    first_charge_id = await _create_charge(customer_id, intended_offset_days=-3)
    second_charge_id = await _create_charge(customer_id, intended_offset_days=0)
    print(
        "✓ planted: duplicate Stripe charges for Acme Corp "
        f"({first_charge_id}, {second_charge_id}) "
        "with metadata {'invoice': 'INV-1042'} and intended 3-day spacing."
    )


if __name__ == "__main__":
    asyncio.run(seed_duplicate_acme_charge())

