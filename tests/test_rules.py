"""Tests for deterministic tier-0 rule detectors."""

from __future__ import annotations

from datetime import UTC, datetime

from vellum.contracts import Transaction
from vellum.rules.domain_match import detect_domain_mismatch
from vellum.rules.duplicate import detect_duplicates
from vellum.rules.policy_cap import detect_policy_violations
from vellum.rules.zombie_saas import detect_zombie_saas


def _txn(
    *,
    txn_id: str,
    vendor_name: str,
    vendor_normalized: str,
    amount_cents: int,
    occurred_at: datetime,
    category: str | None = None,
    description: str = "",
) -> Transaction:
    return Transaction(
        id=txn_id,
        source="stripe",
        amount_cents=amount_cents,
        currency="USD",
        vendor_name=vendor_name,
        vendor_normalized=vendor_normalized,
        description=description,
        occurred_at=occurred_at,
        category=category,
        raw={"source_id": txn_id},
    )


def test_detect_duplicates_positive_case() -> None:
    txns = [
        _txn(
            txn_id="txn_dup_1",
            vendor_name="Acme Corp",
            vendor_normalized="acme corp",
            amount_cents=100000,
            occurred_at=datetime(2026, 1, 10, tzinfo=UTC),
        ),
        _txn(
            txn_id="txn_dup_2",
            vendor_name="Acme Corp",
            vendor_normalized="acme corp",
            amount_cents=101000,  # within 2%
            occurred_at=datetime(2026, 1, 15, tzinfo=UTC),
        ),
    ]
    findings = detect_duplicates(txns)
    assert len(findings) == 1
    assert findings[0].finding_type == "duplicate_payment"
    assert findings[0].severity == "high"
    assert findings[0].confidence == 0.95
    assert findings[0].evidence == [{"transaction_ids": ["txn_dup_1", "txn_dup_2"]}]
    assert findings[0].reasoning_trace == ""


def test_detect_duplicates_negative_case() -> None:
    txns = [
        _txn(
            txn_id="txn_dup_3",
            vendor_name="Acme Corp",
            vendor_normalized="acme corp",
            amount_cents=100000,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _txn(
            txn_id="txn_dup_4",
            vendor_name="Acme Corp",
            vendor_normalized="acme corp",
            amount_cents=110000,  # outside 2%
            occurred_at=datetime(2026, 1, 4, tzinfo=UTC),
        ),
    ]
    assert detect_duplicates(txns) == []


def test_detect_policy_violations_positive_case() -> None:
    txns = [
        _txn(
            txn_id="txn_policy_1",
            vendor_name="Bistro 9",
            vendor_normalized="bistro 9",
            amount_cents=89000,
            occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
            category="meal",
            description="Team dinner, 4 attendees",
        )
    ]
    policy = {"meal_per_person_cap_cents": 15000}
    findings = detect_policy_violations(txns, policy)
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].confidence == 0.99
    assert findings[0].evidence == [{"transaction_ids": ["txn_policy_1"]}]
    assert len(findings[0].suggested_actions) == 1
    assert findings[0].suggested_actions[0].requires_approval is True
    assert findings[0].suggested_actions[0].status == "pending"


def test_detect_policy_violations_negative_case() -> None:
    txns = [
        _txn(
            txn_id="txn_policy_2",
            vendor_name="Cafe Good",
            vendor_normalized="cafe good",
            amount_cents=30000,
            occurred_at=datetime(2026, 2, 2, tzinfo=UTC),
            category="meal",
            description="Lunch for 3 attendees",
        )
    ]
    policy = {"meal_per_person_cap_cents": 15000}
    assert detect_policy_violations(txns, policy) == []


def test_detect_domain_mismatch_positive_case() -> None:
    emails = [
        {
            "vendor_name": "Acme Corp",
            "from_address": "billing@acme-secure-payments.com",
            "body": "Please update bank details for your next invoice.",
            "txn_id": "txn_email_1",
        }
    ]
    vendor_registry = {"Acme Corp": "acme.com"}
    findings = detect_domain_mismatch(emails, vendor_registry)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].confidence == 0.85
    assert findings[0].evidence == [{"transaction_ids": ["txn_email_1"]}]


def test_detect_domain_mismatch_negative_case() -> None:
    emails = [
        {
            "vendor_name": "Acme Corp",
            "from_address": "ap@acme.com",
            "body": "Please update bank details for your next invoice.",
            "txn_id": "txn_email_2",
        }
    ]
    vendor_registry = {"Acme Corp": "acme.com"}
    assert detect_domain_mismatch(emails, vendor_registry) == []


def test_detect_zombie_saas_positive_case() -> None:
    txns = [
        _txn(
            txn_id="txn_saas_1",
            vendor_name="Datadog",
            vendor_normalized="datadog",
            amount_cents=60000,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _txn(
            txn_id="txn_saas_2",
            vendor_name="Datadog",
            vendor_normalized="datadog",
            amount_cents=60500,
            occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
        ),
    ]
    usage_signals = {"datadog": [datetime(2025, 12, 15, tzinfo=UTC).isoformat()]}
    findings = detect_zombie_saas(txns, usage_signals)
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].confidence == 0.7
    assert findings[0].evidence == [{"transaction_ids": ["txn_saas_1", "txn_saas_2"]}]


def test_detect_zombie_saas_negative_case() -> None:
    txns = [
        _txn(
            txn_id="txn_saas_3",
            vendor_name="Datadog",
            vendor_normalized="datadog",
            amount_cents=45000,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _txn(
            txn_id="txn_saas_4",
            vendor_name="Datadog",
            vendor_normalized="datadog",
            amount_cents=45200,
            occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
        ),
    ]
    usage_signals = {"datadog": [datetime(2026, 1, 25, tzinfo=UTC).isoformat()]}
    assert detect_zombie_saas(txns, usage_signals) == []
