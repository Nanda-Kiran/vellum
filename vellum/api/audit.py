"""Audit pack API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])


@router.post("/{period}")
async def build_audit_pack(period: str) -> dict[str, str]:
    """Create an audit pack for a period and return Google Doc URL."""
    _ = period
    raise NotImplementedError("TODO: Generate audit pack and return doc URL.")

