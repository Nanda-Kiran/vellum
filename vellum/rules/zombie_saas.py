"""Tier-0 unused recurring SaaS charge detector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from vellum.contracts import Finding, Transaction


def _amounts_similar(left: int, right: int) -> bool:
    baseline = max(abs(left), abs(right), 1)
    return abs(left - right) <= baseline * 0.05


def _is_monthly_pattern(transactions: list[Transaction]) -> bool:
    if len(transactions) < 2:
        return False
    ordered = sorted(transactions, key=lambda txn: txn.occurred_at)
    for earlier, later in zip(ordered, ordered[1:]):
        days_apart = (later.occurred_at - earlier.occurred_at).days
        if days_apart < 25 or days_apart > 35:
            return False
        if not _amounts_similar(earlier.amount_cents, later.amount_cents):
            return False
    return True


def _has_recent_usage(usage_signals: dict, vendor_name: str, reference_time: datetime) -> bool:
    signals = usage_signals.get(vendor_name)
    if signals is None:
        return False

    if isinstance(signals, (str, datetime)):
        signals = [signals]
    if not isinstance(signals, list):
        return False

    cutoff = reference_time - timedelta(days=30)
    for signal in signals:
        parsed: datetime | None = None
        if isinstance(signal, datetime):
            parsed = signal
        elif isinstance(signal, str):
            try:
                parsed = datetime.fromisoformat(signal.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
        if parsed is not None and parsed >= cutoff:
            return True
    return False


def detect_zombie_saas(txns: list[Transaction], usage_signals: dict) -> list[Finding]:
    """Detect likely monthly subscriptions that show no recent product usage."""
    findings: list[Finding] = []
    txns_by_vendor: dict[str, list[Transaction]] = {}
    for txn in txns:
        txns_by_vendor.setdefault(txn.vendor_normalized, []).append(txn)

    for vendor, vendor_txns in txns_by_vendor.items():
        if not _is_monthly_pattern(vendor_txns):
            continue

        latest_txn = max(vendor_txns, key=lambda txn: txn.occurred_at)
        if _has_recent_usage(usage_signals, vendor, latest_txn.occurred_at):
            continue

        severity = "low" if latest_txn.amount_cents < 50000 else "medium"
        findings.append(
            Finding(
                id=f"find_zombie_saas_{vendor}_{latest_txn.id}",
                agent="reconciliation",
                finding_type="zombie_saas",
                severity=severity,
                confidence=0.7,
                title=f"Unused recurring subscription: {latest_txn.vendor_name}",
                summary="Recurring monthly SaaS charge has no usage signals in the last 30 days.",
                evidence=[{"transaction_ids": [txn.id for txn in vendor_txns]}],
                reasoning_trace="",
                suggested_actions=[],
                created_at=datetime.now(UTC),
            )
        )
    return findings

