"""Tier-0 vendor email domain matcher."""

from __future__ import annotations

from datetime import UTC, datetime

from vellum.contracts import Finding

_RISKY_PHRASES = ("update bank", "new wire", "change account")


def _domain_from_address(address: str) -> str:
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].strip().lower()


def _extract_vendor_name(email: dict, vendor_registry: dict[str, str]) -> str | None:
    explicit_vendor = email.get("vendor_name")
    if isinstance(explicit_vendor, str) and explicit_vendor in vendor_registry:
        return explicit_vendor

    body = str(email.get("body", "")).lower()
    for vendor_name in vendor_registry:
        if vendor_name.lower() in body:
            return vendor_name
    return None


def _extract_txn_ids(email: dict) -> list[str]:
    txn_ids = email.get("txn_ids")
    if isinstance(txn_ids, list):
        return [str(txn_id) for txn_id in txn_ids if str(txn_id)]
    txn_id = email.get("txn_id")
    if txn_id is None:
        return []
    return [str(txn_id)]


def detect_domain_mismatch(emails: list[dict], vendor_registry: dict) -> list[Finding]:
    """Detect risky bank-change emails from domains that mismatch vendor records."""
    findings: list[Finding] = []
    normalized_registry = {str(name): str(domain).lower() for name, domain in vendor_registry.items()}

    for email in emails:
        body = str(email.get("body", "")).lower()
        if not any(phrase in body for phrase in _RISKY_PHRASES):
            continue

        vendor_name = _extract_vendor_name(email, normalized_registry)
        if vendor_name is None:
            continue
        sender_domain = _domain_from_address(str(email.get("from_address", "")))
        verified_domain = normalized_registry.get(vendor_name, "")
        if not sender_domain or not verified_domain or sender_domain == verified_domain:
            continue

        txn_ids = _extract_txn_ids(email)
        findings.append(
            Finding(
                id=f"find_domain_mismatch_{vendor_name}_{len(findings)}",
                agent="forensics",
                finding_type="vendor_domain_mismatch",
                severity="critical",
                confidence=0.85,
                title=f"Domain mismatch for {vendor_name}",
                summary=(
                    f"Sender domain {sender_domain} does not match verified domain "
                    f"{verified_domain} for a bank-change request."
                ),
                evidence=[{"transaction_ids": txn_ids}],
                reasoning_trace="",
                suggested_actions=[],
                created_at=datetime.now(UTC),
            )
        )
    return findings

