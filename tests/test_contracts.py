"""Round-trip serialization tests for shared contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vellum.contracts import Action, Finding, LedgerEntry, Transaction


ACTION_TYPES = (
    "draft_email",
    "cancel_subscription",
    "request_clawback",
    "flag_for_review",
    "create_journal_entry",
)
SEVERITIES = ("info", "low", "medium", "high", "critical")


def _build_transaction() -> Transaction:
    return Transaction(
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


def _build_action(action_type: str) -> Action:
    return Action(
        id=f"act_{action_type}",
        action_type=action_type,
        target={"transaction_id": "txn_1"},
        requires_approval=True,
        status="pending",
    )


def _build_finding(
    *,
    severity: str = "high",
    evidence: list[dict] | None = None,
    suggested_actions: list[Action] | None = None,
) -> Finding:
    return Finding(
        id="find_1",
        agent="reconciliation",
        finding_type="duplicate_payment",
        severity=severity,
        confidence=0.95,
        title="Possible duplicate payment",
        summary="Two matching charges found.",
        evidence=[{"transaction_ids": ["txn_1", "txn_2"]}] if evidence is None else evidence,
        reasoning_trace="deterministic-match",
        suggested_actions=[_build_action("flag_for_review")]
        if suggested_actions is None
        else suggested_actions,
        created_at=datetime.now(UTC),
    )


def test_transaction_round_trip() -> None:
    """Ensure Transaction serializes and deserializes losslessly."""
    transaction = _build_transaction()
    restored = Transaction.model_validate_json(transaction.model_dump_json())
    assert restored == transaction


@pytest.mark.parametrize("action_type", ACTION_TYPES)
def test_action_round_trip_for_all_action_types(action_type: str) -> None:
    """Ensure Action round-trips for every action_type literal."""
    action = _build_action(action_type)
    restored = Action.model_validate_json(action.model_dump_json())
    assert restored == action


@pytest.mark.parametrize("severity", SEVERITIES)
def test_finding_round_trip_for_all_severities(severity: str) -> None:
    """Ensure Finding round-trips for every severity literal."""
    finding = _build_finding(severity=severity)
    restored = Finding.model_validate_json(finding.model_dump_json())
    assert restored == finding


def test_finding_round_trip_with_empty_evidence_list() -> None:
    """Ensure Finding supports and preserves an empty evidence list."""
    finding = _build_finding(evidence=[])
    restored = Finding.model_validate_json(finding.model_dump_json())
    assert restored == finding
    assert restored.evidence == []


def test_ledger_entry_round_trip_with_nested_models() -> None:
    """Ensure LedgerEntry round-trips with nested Finding and Action."""
    finding = _build_finding()
    entry = LedgerEntry(
        finding=finding,
        slack_message_ts=None,
        approver=None,
        audit_pack_id=None,
    )
    restored = LedgerEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry

