"""Compliance agent for policy and control validation."""

from __future__ import annotations

import json

from vellum.contracts import Finding, Transaction
from vellum.groq_client import call
from vellum.logging_setup import get_logger
from vellum.rules.policy_cap import detect_policy_violations

logger = get_logger(__name__)
_MAX_POLICY_TAGS = 4


async def run_compliance_agent(transactions: list[Transaction], policy: dict | None = None) -> list[Finding]:
    """Check activity against policy caps with optional fast-model triage."""
    effective_policy = policy or {"meal_per_person_cap_cents": 15000}
    findings = detect_policy_violations(transactions, effective_policy)
    # Keep one finding per id to avoid repeated model calls for duplicated rows.
    unique_findings: list[Finding] = []
    seen_ids: set[str] = set()
    for finding in findings:
        if finding.id in seen_ids:
            continue
        seen_ids.add(finding.id)
        unique_findings.append(finding)
    findings = unique_findings
    if not findings:
        return []

    schema = json.dumps(
        {
            "type": "object",
            "properties": {"policy_area": {"type": "string"}},
            "required": ["policy_area"],
        }
    )
    for index, finding in enumerate(findings):
        if index >= _MAX_POLICY_TAGS:
            logger.info(
                "compliance.policy_tag_skipped",
                skipped_count=len(findings) - _MAX_POLICY_TAGS,
            )
            break
        try:
            response = await call(
                "fast",
                [
                    {
                        "role": "system",
                        "content": "Tag the compliance policy area in 1-3 words.",
                    },
                    {
                        "role": "user",
                        "content": finding.model_dump_json(),
                    },
                ],
                schema=schema,
                cacheable=True,
                stream=False,
            )
            if isinstance(response, dict):
                logger.info(
                    "compliance.policy_tag",
                    finding_id=finding.id,
                    policy_area=str(response.get("policy_area", "")),
                )
        except Exception:
            logger.info("compliance.fast_triage_failed", finding_id=finding.id)
    return findings

