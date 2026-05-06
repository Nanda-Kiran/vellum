"""Async Stripe integration wrapper."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import stripe

from vellum.contracts import Transaction
from vellum.settings import get_settings


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_for_json(item) for key, item in value.items()}
    if hasattr(value, "to_dict_recursive"):
        return _normalize_for_json(value.to_dict_recursive())
    if hasattr(value, "to_dict"):
        return _normalize_for_json(value.to_dict())
    raw_data = getattr(value, "_data", None)
    if isinstance(raw_data, dict):
        return _normalize_for_json(raw_data)
    return str(value)


def _to_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(_normalize_for_json(payload))
    if hasattr(payload, "to_dict_recursive"):
        normalized = _normalize_for_json(payload.to_dict_recursive())
        if isinstance(normalized, dict):
            return dict(normalized)
        return {}
    raw_data = getattr(payload, "_data", None)
    if isinstance(raw_data, dict):
        normalized = _normalize_for_json(raw_data)
        if isinstance(normalized, dict):
            return dict(normalized)
        return {}
    normalized = _normalize_for_json(payload)
    if isinstance(normalized, dict):
        return dict(normalized)
    return {}


def _map_charge_to_transaction(charge: Any, customer_name: str | None) -> Transaction:
    charge_dict = _to_dict(charge)
    created_at = datetime.fromtimestamp(int(charge_dict.get("created", 0)), tz=UTC)
    vendor_name = (
        customer_name
        or charge_dict.get("billing_details", {}).get("name")
        or charge_dict.get("description")
        or "Unknown customer"
    )
    return Transaction(
        id=str(charge_dict.get("id", "")),
        source="stripe",
        amount_cents=int(charge_dict.get("amount", 0)),
        currency=str(charge_dict.get("currency", "usd")).upper(),
        vendor_name=str(vendor_name),
        vendor_normalized=str(vendor_name),
        description=str(
            charge_dict.get("description")
            or charge_dict.get("statement_descriptor")
            or vendor_name
        ),
        occurred_at=created_at,
        category=None,
        raw=charge_dict,
    )


async def pull_recent_charges(days_back: int = 30) -> list[Transaction]:
    """Pull recent Stripe charges and map them into contracts.Transaction."""
    settings = get_settings()
    if not settings.stripe_api_key:
        return []

    stripe.api_key = settings.stripe_api_key
    since_ts = int((datetime.now(UTC) - timedelta(days=days_back)).timestamp())
    charges_response = await asyncio.to_thread(
        stripe.Charge.list,
        limit=100,
        created={"gte": since_ts},
    )
    charges_container = _to_dict(charges_response)
    charges = list(charges_container.get("data", []))

    customer_name_cache: dict[str, str | None] = {}
    transactions: list[Transaction] = []
    for charge in charges:
        charge_dict = _to_dict(charge)
        customer_id = charge_dict.get("customer")
        customer_name: str | None = None
        if isinstance(customer_id, str) and customer_id:
            if customer_id not in customer_name_cache:
                customer = await asyncio.to_thread(stripe.Customer.retrieve, customer_id)
                customer_dict = _to_dict(customer)
                customer_name_cache[customer_id] = (
                    str(customer_dict.get("name")) if customer_dict.get("name") else None
                )
            customer_name = customer_name_cache.get(customer_id)
        transactions.append(_map_charge_to_transaction(charge_dict, customer_name))
    return transactions


async def fetch_stripe_charges() -> list[Transaction]:
    """Compatibility wrapper for ingestion pipeline callers."""
    return await pull_recent_charges(days_back=30)

