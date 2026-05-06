"""Forensics agent for high-signal fraud pattern analysis."""

from __future__ import annotations

import asyncio
import json

from vellum.contracts import Finding, Transaction
from vellum.groq_client import call
from vellum.logging_setup import get_logger
from vellum.rules.domain_match import detect_domain_mismatch

logger = get_logger(__name__)
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_MAX_LLM_ENRICHMENTS = 8
_ENRICHMENT_TIMEOUT_SECONDS = 8.0


def _max_severity(base: str, proposed: str) -> str:
    base_rank = _SEVERITY_RANK.get(base, 0)
    proposed_rank = _SEVERITY_RANK.get(proposed, base_rank)
    return proposed if proposed_rank > base_rank else base


async def _enrich_finding_with_reasoning(candidate: Finding, transactions: list[Transaction]) -> Finding:
    related_txn_ids: list[str] = []
    for evidence_item in candidate.evidence:
        transaction_ids = evidence_item.get("transaction_ids")
        if isinstance(transaction_ids, list):
            related_txn_ids.extend(str(txn_id) for txn_id in transaction_ids)

    related_transactions = [
        txn.model_dump(mode="json") for txn in transactions if txn.id in set(related_txn_ids)
    ]
    enrichment_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "reasoning_trace": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["info", "low", "medium", "high", "critical"],
                },
            },
            "required": ["reasoning_trace"],
        }
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are Vellum's forensics reviewer. Return ONLY JSON with reasoning_trace and optional severity. "
                "Keep reasoning_trace concise, specific, and evidence-grounded. "
                "Only upgrade severity when the context materially increases risk."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "candidate_finding": candidate.model_dump(mode="json"),
                    "related_transactions": related_transactions,
                }
            ),
        },
    ]
    response = await call(
        "smart",
        messages,
        schema=enrichment_schema,
        cacheable=False,
        stream=False,
    )
    if not isinstance(response, dict) or not str(response.get("reasoning_trace", "")).strip():
        # One strict retry before failing back to deterministic text.
        retry_messages = [
            messages[0],
            {
                "role": "user",
                "content": (
                    f"{messages[1]['content']}\n\n"
                    "Retry and return valid JSON only. "
                    "Required field: reasoning_trace (non-empty string)."
                ),
            },
        ]
        response = await call(
            "smart",
            retry_messages,
            schema=enrichment_schema,
            cacheable=False,
            stream=False,
        )
    if not isinstance(response, dict):
        return candidate
    proposed_severity = str(response.get("severity") or candidate.severity)
    proposed_reasoning = str(response.get("reasoning_trace") or "").strip()
    return candidate.model_copy(
        update={
            "severity": _max_severity(candidate.severity, proposed_severity),
            "confidence": candidate.confidence,
            "reasoning_trace": proposed_reasoning or candidate.reasoning_trace,
        }
    )


async def run_forensics_agent(
    transactions: list[Transaction],
    candidate_findings: list[Finding],
    emails: list[dict] | None = None,
    vendor_registry: dict[str, str] | None = None,
) -> list[Finding]:
    """Enrich rule-detected findings with SMART reasoning and optional severity upgrades."""
    additional_candidates = detect_domain_mismatch(emails or [], vendor_registry or {})
    findings = [*candidate_findings, *additional_candidates]
    if not findings:
        return []

    enriched: list[Finding] = []
    for index, candidate in enumerate(findings):
        if index >= _MAX_LLM_ENRICHMENTS:
            logger.info(
                "forensics.enrichment_skipped",
                finding_id=candidate.id,
                reason="llm_enrichment_cap_reached",
            )
            enriched.append(
                candidate.model_copy(
                    update={
                        "reasoning_trace": candidate.reasoning_trace
                        or "Deterministic signal retained; enrichment skipped for performance.",
                    }
                )
            )
            continue
        try:
            enriched_finding = await asyncio.wait_for(
                _enrich_finding_with_reasoning(candidate, transactions),
                timeout=_ENRICHMENT_TIMEOUT_SECONDS,
            )
            enriched.append(enriched_finding)
        except TimeoutError:
            logger.info(
                "forensics.enrichment_timeout",
                finding_id=candidate.id,
                timeout_seconds=_ENRICHMENT_TIMEOUT_SECONDS,
            )
            enriched.append(
                candidate.model_copy(
                    update={
                        "reasoning_trace": candidate.reasoning_trace
                        or "Deterministic signal retained; enrichment timed out.",
                    }
                )
            )
        except Exception as exc:
            logger.info(
                "forensics.enrichment_failed",
                finding_id=candidate.id,
                error=str(exc),
            )
            enriched.append(
                candidate.model_copy(
                    update={
                        "reasoning_trace": candidate.reasoning_trace
                        or "Deterministic signal retained; LLM enrichment unavailable.",
                    }
                )
            )
    return enriched

