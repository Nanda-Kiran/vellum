"""Round-trip serialization tests for shared contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from vellum.contracts import Action, Finding, LedgerEntry, Transaction


def test_transaction_round_trip() -> None:
    """Ensure Transaction serializes and deserializes losslessly."""
    transaction = Transaction(
        id="txn_1",
        source="stripe",
        amount_cents=1000,
        currency="USD",
        vendor_name="Acme Corp",
        vendor_normalized="acme corp",
        description="Test charge",
        occurred_at=datetime.now(UTC),
        category="software",
        raw={"source_id": "ch_123"},
    )
    restored = Transaction.model_validate_json(transaction.model_dump_json())
    assert restored == transaction


def test_finding_and_ledger_entry_round_trip() -> None:
    """Ensure nested Finding, Action, and LedgerEntry round-trip correctly."""
    action = Action(
        id="act_1",
        action_type="flag_for_review",
        target={"transaction_id": "txn_1"},
        requires_approval=True,
        status="pending",
    )
    finding = Finding(
        id="find_1",
        agent="reconciliation",
        finding_type="duplicate_payment",
        severity="high",
        confidence=0.95,
        title="Possible duplicate payment",
        summary="Two matching charges found.",
        evidence=[{"transaction_ids": ["txn_1", "txn_2"]}],
        reasoning_trace="deterministic-match",
        suggested_actions=[action],
        created_at=datetime.now(UTC),
    )
    entry = LedgerEntry(
        finding=finding,
        slack_message_ts=None,
        approver=None,
        audit_pack_id=None,
    )
    restored = LedgerEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry

