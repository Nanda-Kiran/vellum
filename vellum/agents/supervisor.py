"""LangGraph supervisor that orchestrates specialist agents."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from vellum.agents.compliance import run_compliance_agent
from vellum.agents.forensics import run_forensics_agent
from vellum.agents.ingestion import run_ingestion_agent
from vellum.agents.reconciliation import run_reconciliation_agent
from vellum.agents.reporting import run_reporting_agent
from vellum.contracts import Action, Finding, Transaction
from vellum.logging_setup import get_logger

logger = get_logger(__name__)


class SupervisorState(TypedDict):
    """Shared orchestration state passed through the supervisor graph."""

    user_message: str | None
    new_txns: list[Transaction]
    findings: list[Finding]
    pending_actions: list[Action]
    final_response: str | None


async def ingestion_node(state: SupervisorState) -> SupervisorState:
    """Collect transactions when state was not pre-seeded by scheduler."""
    if state["new_txns"]:
        return state
    new_txns = await run_ingestion_agent([])
    if not new_txns:
        return {
            **state,
            "new_txns": [],
            "final_response": state["final_response"] or "No new transactions were ingested.",
        }
    return {**state, "new_txns": new_txns}


async def reconciliation_node(state: SupervisorState) -> SupervisorState:
    """Run deterministic reconciliation checks to seed candidate findings."""
    findings = await run_reconciliation_agent(state["new_txns"])
    if not findings:
        return {
            **state,
            "findings": [],
            "pending_actions": [],
            "final_response": state["final_response"] or "No findings detected for this run.",
        }
    pending_actions: list[Action] = []
    for finding in findings:
        pending_actions.extend(finding.suggested_actions)
    return {**state, "findings": findings, "pending_actions": pending_actions}


async def forensics_compliance_node(state: SupervisorState) -> SupervisorState:
    """Augment candidates with compliance checks and SMART-model forensics reasoning."""
    compliance_findings = await run_compliance_agent(state["new_txns"])
    merged_candidates = [*state["findings"], *compliance_findings]
    enhanced_findings = await run_forensics_agent(
        state["new_txns"],
        merged_candidates,
        emails=[],
        vendor_registry={},
    )
    pending_actions: list[Action] = []
    for finding in enhanced_findings:
        pending_actions.extend(finding.suggested_actions)
    return {**state, "findings": enhanced_findings, "pending_actions": pending_actions}


async def reporting_node(state: SupervisorState) -> SupervisorState:
    """Build period report and hydrate final response for Slack/API callers."""
    period = "last_30_days"
    if state["user_message"] and len(state["user_message"].strip()) == 7 and "-" in state["user_message"]:
        period = state["user_message"].strip()
    audit_pack = await run_reporting_agent(period)
    summary = str(audit_pack.get("executive_summary", ""))
    if not summary:
        summary = "No findings available for the selected period."
    return {**state, "final_response": summary}


async def route_node(state: SupervisorState) -> SupervisorState:
    """Route state without mutating it; conditional edges decide next node."""
    logger.info(
        "supervisor.route",
        has_new_txns=bool(state["new_txns"]),
        finding_count=len(state["findings"]),
        has_response=state["final_response"] is not None,
    )
    return state


def _next_step(state: SupervisorState) -> Literal["ingestion", "reconciliation", "forensics_compliance", "reporting", "__end__"]:
    if state["final_response"] is not None:
        return "__end__"
    if not state["new_txns"] and not state["findings"]:
        return "ingestion"
    if state["new_txns"] and not state["findings"]:
        return "reconciliation"
    if state["findings"] and any(not finding.reasoning_trace for finding in state["findings"]):
        return "forensics_compliance"
    return "reporting"


def build_supervisor_graph() -> Any:
    """Create and compile the LangGraph supervisor StateGraph."""
    graph = StateGraph(SupervisorState)
    graph.add_node("route", route_node)
    graph.add_node("ingestion", ingestion_node)
    graph.add_node("reconciliation", reconciliation_node)
    graph.add_node("forensics_compliance", forensics_compliance_node)
    graph.add_node("reporting", reporting_node)
    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", _next_step)
    graph.add_edge("ingestion", "route")
    graph.add_edge("reconciliation", "route")
    graph.add_edge("forensics_compliance", "route")
    graph.add_edge("reporting", END)
    return graph.compile()


async def run_supervisor(state: dict[str, Any]) -> dict[str, Any]:
    """Execute the supervisor graph over validated initial state."""
    initial_state: SupervisorState = {
        "user_message": state.get("user_message"),
        "new_txns": state.get("new_txns", []),
        "findings": state.get("findings", []),
        "pending_actions": state.get("pending_actions", []),
        "final_response": state.get("final_response"),
    }
    app = build_supervisor_graph()
    result = await app.ainvoke(initial_state)
    return dict(result)

