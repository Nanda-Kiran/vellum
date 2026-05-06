"""Tier-0 expense policy cap checker."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from vellum.contracts import Action, Finding, Transaction

_ATTENDEES_PATTERN = re.compile(r"\b(\d+)\s+attendees?\b", flags=re.IGNORECASE)


def _extract_attendees(description: str) -> int | None:
    match = _ATTENDEES_PATTERN.search(description)
    if not match:
        return None
    attendees = int(match.group(1))
    return attendees if attendees > 0 else None


def detect_policy_violations(txns: list[Transaction], policy: dict) -> list[Finding]:
    """Detect meal transactions exceeding per-person policy limits."""
    per_person_cap = policy.get("meal_per_person_cap_cents")
    if not isinstance(per_person_cap, int) or per_person_cap <= 0:
        return []

    findings: list[Finding] = []
    for txn in txns:
        if txn.category != "meal":
            continue
        attendees = _extract_attendees(txn.description)
        if attendees is None:
            continue
        cap_total = per_person_cap * attendees
        if txn.amount_cents <= cap_total:
            continue
        findings.append(
            Finding(
                id=f"find_policy_cap_{txn.id}",
                agent="compliance",
                finding_type="policy_cap_violation",
                severity="medium",
                confidence=0.99,
                title="Meal exceeds policy per-person cap",
                summary=(
                    f"Meal expense of {txn.amount_cents} cents exceeds cap of {cap_total} "
                    f"cents for {attendees} attendees."
                ),
                evidence=[{"transaction_ids": [txn.id]}],
                reasoning_trace="",
                suggested_actions=[
                    Action(
                        id=f"act_policy_cap_review_{txn.id}",
                        action_type="flag_for_review",
                        target={
                            "transaction_id": txn.id,
                            "policy": "meal_per_person_cap_cents",
                            "amount_cents": txn.amount_cents,
                            "cap_cents": cap_total,
                        },
                        requires_approval=True,
                        status="pending",
                    )
                ],
                created_at=datetime.now(UTC),
            )
        )
    return findings

