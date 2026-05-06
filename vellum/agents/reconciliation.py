"""Reconciliation agent for deterministic payment consistency checks."""

from __future__ import annotations

import asyncio
import json

from vellum.contracts import Finding, Transaction
from vellum.groq_client import call
from vellum.logging_setup import get_logger
from vellum.rules.duplicate import detect_duplicates
from vellum.rules.zombie_saas import detect_zombie_saas

logger = get_logger(__name__)
_MAX_TRIAGE_FINDINGS = 5
_TRIAGE_TIMEOUT_SECONDS = 6.0


async def run_reconciliation_agent(transactions: list[Transaction]) -> list[Finding]:
    """Run deterministic checks and optionally triage with fast-model labels."""
    if not transactions:
        return []

    findings: list[Finding] = []
    findings.extend(detect_duplicates(transactions))
    findings.extend(detect_zombie_saas(transactions, usage_signals={}))

    if not findings:
        return []

    triage_schema = json.dumps(
        {
            "type": "object",
            "properties": {"priority": {"type": "string"}},
            "required": ["priority"],
        }
    )
    for index, finding in enumerate(findings):
        if index >= _MAX_TRIAGE_FINDINGS:
            logger.info(
                "reconciliation.fast_triage_skipped",
                skipped_count=len(findings) - _MAX_TRIAGE_FINDINGS,
            )
            break
        try:
            triage = await asyncio.wait_for(
                call(
                    "fast",
                    [
                        {
                            "role": "system",
                            "content": "Classify this finding priority as low, medium, or high.",
                        },
                        {
                            "role": "user",
                            "content": finding.model_dump_json(),
                        },
                    ],
                    schema=triage_schema,
                    cacheable=True,
                    stream=False,
                ),
                timeout=_TRIAGE_TIMEOUT_SECONDS,
            )
            if isinstance(triage, dict):
                logger.info(
                    "reconciliation.triage",
                    finding_id=finding.id,
                    priority=str(triage.get("priority", "")),
                )
        except TimeoutError:
            logger.info(
                "reconciliation.fast_triage_timeout",
                finding_id=finding.id,
                timeout_seconds=_TRIAGE_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.info("reconciliation.fast_triage_failed", finding_id=finding.id)
    return findings

