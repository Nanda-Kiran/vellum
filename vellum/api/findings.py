"""Findings API endpoints for review and action workflows."""

from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from vellum.contracts import Finding

router = APIRouter(prefix="/findings", tags=["findings"])


class FindingDecisionRequest(BaseModel):
    """Request model for approving or rejecting a finding action."""

    finding_id: str
    approver: str


@router.get("/", response_model=list[Finding])
async def get_findings() -> list[Finding]:
    """List findings awaiting review."""
    raise NotImplementedError("TODO: Fetch findings from ledger.")


@router.post("/approve")
async def approve_finding(payload: FindingDecisionRequest) -> dict[str, str]:
    """Approve a finding action from Slack or API."""
    _ = payload
    raise NotImplementedError("TODO: Mark finding as approved in ledger.")


@router.post("/reject")
async def reject_finding(payload: FindingDecisionRequest) -> dict[str, str]:
    """Reject a finding action from Slack or API."""
    _ = payload
    raise NotImplementedError("TODO: Mark finding as rejected in ledger.")

