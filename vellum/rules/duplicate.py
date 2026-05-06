"""Tier-0 duplicate payment detector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from vellum.contracts import Finding, Transaction

_WINDOW_DAYS = 7
_MAX_FINDINGS_PER_VENDOR = 5


def _amounts_within_percent(left: int, right: int, percent: float) -> bool:
    baseline = max(abs(left), abs(right), 1)
    return abs(left - right) <= baseline * percent


def detect_duplicates(txns: list[Transaction]) -> list[Finding]:
    """Detect likely duplicate charges based on vendor, timing, and amount similarity."""
    findings: list[Finding] = []
    txns_by_vendor: dict[str, list[Transaction]] = {}
    for txn in txns:
        txns_by_vendor.setdefault(txn.vendor_normalized, []).append(txn)

    for vendor_txns in txns_by_vendor.values():
        ordered = sorted(vendor_txns, key=lambda txn: txn.occurred_at)
        used_ids: set[str] = set()
        per_vendor_count = 0
        for index, first in enumerate(ordered):
            if first.id in used_ids or per_vendor_count >= _MAX_FINDINGS_PER_VENDOR:
                continue
            best_match: Transaction | None = None
            best_delta: timedelta | None = None
            for second in ordered[index + 1 :]:
                if second.id in used_ids:
                    continue
                delta = second.occurred_at - first.occurred_at
                if delta > timedelta(days=_WINDOW_DAYS):
                    break
                if not _amounts_within_percent(first.amount_cents, second.amount_cents, 0.02):
                    continue
                if best_delta is None or delta < best_delta:
                    best_match = second
                    best_delta = delta
            if best_match is None:
                continue
            max_amount = max(first.amount_cents, best_match.amount_cents)
            findings.append(
                Finding(
                    id=f"find_duplicate_{first.id}_{best_match.id}",
                    agent="reconciliation",
                    finding_type="duplicate_payment",
                    severity="high" if max_amount > 100000 else "medium",
                    confidence=0.95,
                    title=f"Possible duplicate payment to {first.vendor_name}",
                    summary="Two similar vendor charges occurred within seven days.",
                    evidence=[{"transaction_ids": [first.id, best_match.id]}],
                    reasoning_trace="",
                    suggested_actions=[],
                    created_at=datetime.now(UTC),
                )
            )
            used_ids.add(first.id)
            used_ids.add(best_match.id)
            per_vendor_count += 1
    return findings

