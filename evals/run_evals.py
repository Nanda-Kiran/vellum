"""Evaluation runner for fixed Vellum demo scenarios."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from vellum.agents.supervisor import run_supervisor
from vellum.contracts import Finding, Transaction
from vellum.ledger import LedgerStore, close_pool
from vellum.rules.domain_match import detect_domain_mismatch
from vellum.rules.policy_cap import detect_policy_violations

GREEN = "\u2705"
RED = "\u274c"
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    notes: str


def _load_cases(cases_path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    path = Path(cases_path)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def _transactions_from_input(payload: dict[str, Any]) -> list[Transaction]:
    txns_raw = payload.get("txns", [])
    return [Transaction.model_validate(txn) for txn in txns_raw]


def _seed_findings(payload: dict[str, Any], txns: list[Transaction]) -> list[Finding]:
    findings: list[Finding] = []
    if payload.get("seed_policy_from_rule"):
        policy = payload.get("policy", {"meal_per_person_cap_cents": 15000})
        findings.extend(detect_policy_violations(txns, policy))
    if payload.get("seed_domain_from_rule"):
        emails = payload.get("emails", [])
        vendor_registry = payload.get("vendor_registry", {})
        findings.extend(detect_domain_mismatch(emails, vendor_registry))
    return findings


def _finding_matches_expectation(findings: list[Finding], expected: dict[str, Any]) -> tuple[bool, str]:
    finding_type = expected.get("finding_type")
    min_severity = expected.get("min_severity")
    if finding_type is None:
        if findings:
            return False, f"expected no findings, got {len(findings)}"
        return True, "no findings as expected"

    matched = [finding for finding in findings if finding.finding_type == finding_type]
    if not matched:
        observed_types = sorted({finding.finding_type for finding in findings})
        return False, f"missing finding_type={finding_type}; observed={observed_types}"

    if min_severity:
        min_rank = SEVERITY_RANK.get(str(min_severity), -1)
        if all(SEVERITY_RANK.get(finding.severity, -1) < min_rank for finding in matched):
            observed = [finding.severity for finding in matched]
            return (
                False,
                f"finding_type={finding_type} below min_severity={min_severity}; observed={observed}",
            )
    return True, f"matched finding_type={finding_type}"


def _routing_matches_expectation(findings: list[Finding], expected: dict[str, Any]) -> tuple[bool, str]:
    route_expected = expected.get("route")
    if not route_expected:
        return True, "no routing assertion"

    has_forensics = any(finding.finding_type == "vendor_domain_mismatch" for finding in findings)
    has_compliance = any(finding.finding_type == "policy_cap_violation" for finding in findings)

    if route_expected == "forensics":
        passed = has_forensics and not has_compliance
    elif route_expected == "compliance":
        passed = has_compliance and not has_forensics
    elif route_expected == "both":
        passed = has_forensics and has_compliance
    else:
        return False, f"unknown route expectation: {route_expected}"
    return passed, f"route expected={route_expected}, got forensics={has_forensics}, compliance={has_compliance}"


async def _run_case(case: dict[str, Any]) -> EvalResult:
    payload = case.get("input", {})
    txns = _transactions_from_input(payload)
    seeded_findings = _seed_findings(payload, txns)

    # Fresh in-memory ledger for each isolated case.
    in_memory_ledger = LedgerStore(":memory:")
    await in_memory_ledger.initialize()

    async def _reporting_stub(period: str) -> dict[str, Any]:
        _ = period
        _ = in_memory_ledger
        return {"executive_summary": "eval summary"}

    with patch("vellum.agents.supervisor.run_reporting_agent", _reporting_stub):
        result_state = await run_supervisor(
            {
                "user_message": payload.get("user_message"),
                "new_txns": txns,
                "findings": seeded_findings,
                "pending_actions": [],
                "final_response": None,
            }
        )

    findings = result_state.get("findings", [])
    finding_passed, finding_note = _finding_matches_expectation(findings, case.get("expected", {}))
    route_passed, route_note = _routing_matches_expectation(findings, case.get("expected", {}))
    passed = finding_passed and route_passed
    notes = f"{finding_note}; {route_note}"
    return EvalResult(case_id=str(case["id"]), passed=passed, notes=notes)


async def run_evals(cases_path: str) -> list[dict[str, Any]]:
    """Execute evaluation scenarios and return scored results."""
    cases = _load_cases(cases_path)
    results: list[EvalResult] = []
    for case in cases:
        results.append(await _run_case(case))
    return [{"id": r.case_id, "passed": r.passed, "notes": r.notes} for r in results]


def _print_results(results: list[dict[str, Any]]) -> bool:
    all_passed = True
    for result in results:
        passed = bool(result["passed"])
        icon = GREEN if passed else RED
        if not passed:
            all_passed = False
        print(f"{icon} {result['id']} - {result['notes']}")
    return all_passed


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run Vellum deterministic eval cases.")
    parser.add_argument("--cases", default="evals/cases.jsonl", help="Path to JSONL eval cases")
    args = parser.parse_args()
    try:
        results = await run_evals(args.cases)
        return 0 if _print_results(results) else 1
    finally:
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

