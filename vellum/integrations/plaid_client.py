"""Async Plaid integration wrapper."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from plaid import ApiClient
from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.transactions_get_request import TransactionsGetRequest

from vellum.contracts import Transaction
from vellum.logging_setup import get_logger
from vellum.settings import get_settings

logger = get_logger(__name__)
_SANDBOX_INSTITUTION_ID = "ins_109508"


def _response_get(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _build_plaid_client() -> plaid_api.PlaidApi:
    settings = get_settings()
    configuration = Configuration(
        host=f"https://{settings.plaid_env}.plaid.com",
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    api_client = ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def _parse_plaid_date(raw: str) -> datetime:
    parsed = date.fromisoformat(raw)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _map_plaid_txn(raw_txn: Any) -> Transaction:
    raw_dict = raw_txn.to_dict() if hasattr(raw_txn, "to_dict") else dict(raw_txn)
    vendor_name = str(raw_dict.get("merchant_name") or raw_dict.get("name") or "Unknown vendor")
    occurred_raw = str(raw_dict.get("date"))
    return Transaction(
        id=str(raw_dict.get("transaction_id") or raw_dict.get("pending_transaction_id") or ""),
        source="plaid",
        amount_cents=int(float(raw_dict.get("amount", 0.0)) * 100),
        currency=str(raw_dict.get("iso_currency_code") or "USD"),
        vendor_name=vendor_name,
        vendor_normalized=vendor_name,
        description=str(raw_dict.get("name") or vendor_name),
        occurred_at=_parse_plaid_date(occurred_raw),
        category=str(raw_dict.get("personal_finance_category", {}).get("primary")) if raw_dict.get("personal_finance_category") else None,
        raw=raw_dict,
    )


async def create_sandbox_link_token() -> str:
    """Create a Plaid Link token for sandbox OAuth-free onboarding."""
    client = _build_plaid_client()
    request = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id="vellum-sandbox-user"),
        client_name="Vellum",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
    )
    response = await asyncio.to_thread(client.link_token_create, request)
    return str(_response_get(response, "link_token", ""))


async def exchange_public_token(public_token: str) -> str:
    """Exchange a short-lived Plaid public token for an access token."""
    client = _build_plaid_client()
    response = await asyncio.to_thread(
        client.item_public_token_exchange,
        ItemPublicTokenExchangeRequest(public_token=public_token),
    )
    return str(_response_get(response, "access_token", ""))


async def pull_recent_transactions(access_token: str, days_back: int = 30) -> list[Transaction]:
    """Pull recent Plaid transactions and map to contracts.Transaction."""
    client = _build_plaid_client()
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    request = TransactionsGetRequest(
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
    )
    retry_delays = (1, 2, 4, 8)
    last_exc: Exception | None = None
    for attempt, delay in enumerate((*retry_delays, 0)):
        try:
            response = await asyncio.to_thread(client.transactions_get, request)
            transactions = _response_get(response, "transactions", [])
            return [_map_plaid_txn(txn) for txn in transactions]
        except Exception as exc:  # Plaid SDK exception types vary by version.
            last_exc = exc
            if "PRODUCT_NOT_READY" in str(exc) and attempt < len(retry_delays):
                await asyncio.sleep(delay)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    return []


async def fetch_plaid_transactions() -> list[Transaction]:
    """Fetch recent sandbox transactions using Plaid's pre-baked institution item."""
    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        return []

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
    try:
        return await pull_recent_transactions(access_token, days_back=30)
    except Exception as exc:
        logger.info("plaid.pull_recent_transactions_failed", error=str(exc))
        return []

