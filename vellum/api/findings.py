"""Findings API endpoints for review and action workflows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from fastapi import APIRouter

from vellum.contracts import Finding
from vellum.ledger import get_findings as ledger_get_findings
from vellum.ledger import update_action_status

router = APIRouter(prefix="/findings", tags=["findings"])


class FindingDecisionRequest(BaseModel):
    """Request model for approving or rejecting a finding action."""

    finding_id: str
    approver: str


class FindingActionDecisionRequest(BaseModel):
    """Decision payload for a finding-level approval or rejection."""

    decision: Literal["approve", "reject"]
    user: str


@router.get("/", response_model=list[Finding])
async def get_findings() -> list[Finding]:
    """List findings awaiting review."""
    return await ledger_get_findings(filters={"status": "open"})


@router.post("/approve")
async def approve_finding(payload: FindingDecisionRequest) -> dict[str, str]:
    """Approve a finding action from Slack or API."""
    findings = await ledger_get_findings(filters={"id": payload.finding_id, "limit": 1})
    if not findings:
        return {"status": "not_found", "finding_id": payload.finding_id}
    finding = findings[0]
    for action in finding.suggested_actions:
        if action.requires_approval:
            await update_action_status(action.id, "approved", approver=payload.approver)
    return {"status": "approved", "finding_id": payload.finding_id}


@router.post("/reject")
async def reject_finding(payload: FindingDecisionRequest) -> dict[str, str]:
    """Reject a finding action from Slack or API."""
    findings = await ledger_get_findings(filters={"id": payload.finding_id, "limit": 1})
    if not findings:
        return {"status": "not_found", "finding_id": payload.finding_id}
    finding = findings[0]
    for action in finding.suggested_actions:
        if action.requires_approval:
            await update_action_status(action.id, "rejected", approver=payload.approver)
    return {"status": "rejected", "finding_id": payload.finding_id}


@router.post("/{finding_id}/decision")
async def decide_finding(
    finding_id: str,
    payload: FindingActionDecisionRequest,
) -> dict[str, str]:
    """Handle Slack action button decisions for a finding."""
    findings = await ledger_get_findings(filters={"id": finding_id, "limit": 1})
    if not findings:
        return {"status": "not_found", "finding_id": finding_id}
    finding = findings[0]
    target_status = "approved" if payload.decision == "approve" else "rejected"
    for action in finding.suggested_actions:
        if action.requires_approval:
            await update_action_status(action.id, target_status, approver=payload.user)
    return {"status": target_status, "finding_id": finding_id}

