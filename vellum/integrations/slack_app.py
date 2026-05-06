"""Slack Bolt Socket Mode app wiring."""

from __future__ import annotations

from typing import Any

import httpx
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from vellum.contracts import Finding
from vellum.groq_client import call
from vellum.integrations.slack_stream import stream_to_slack
from vellum.ledger import get_findings, get_recent_findings, write_finding, write_slack_message_ts
from vellum.logging_setup import get_logger
from vellum.settings import VellumSettings, get_settings

logger = get_logger(__name__)
_SEVERITY_EMOJI = {
    "info": ":large_blue_circle:",
    "low": ":large_green_circle:",
    "medium": ":large_yellow_circle:",
    "high": ":large_orange_circle:",
    "critical": ":red_circle:",
}
_WEB_CLIENT: AsyncWebClient | None = None
_PLACEHOLDER_REASONING_SNIPPETS = (
    "deterministic signal retained",
    "reasoning trace is not available yet",
    "enrichment unavailable",
    "enrichment timed out",
    "enrichment skipped",
)


def _web_client() -> AsyncWebClient:
    global _WEB_CLIENT
    if _WEB_CLIENT is None:
        settings = get_settings()
        _WEB_CLIENT = AsyncWebClient(token=settings.slack_bot_token)
    return _WEB_CLIENT


def _extract_period(raw: str | None) -> str:
    cleaned = (raw or "").strip()
    return cleaned or "last_30_days"


def _requires_approval(finding: Finding) -> bool:
    return any(action.requires_approval for action in finding.suggested_actions)


def _decision_blocks(
    blocks: list[dict[str, Any]],
    decision: str,
    user_id: str | None,
) -> list[dict[str, Any]]:
    label = "Approved" if decision == "approve" else "Rejected"
    actor = f"<@{user_id}>" if user_id else "unknown user"
    updated_blocks: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") == "actions":
            updated_blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"*{label}* by {actor}"},
                    ],
                }
            )
        else:
            updated_blocks.append(block)
    return updated_blocks


async def _forward_json(settings: VellumSettings, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{settings.vellum_api_base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return dict(response.json())
        return {"text": response.text}


async def _llm_reasoning_trace(finding: Finding) -> str:
    prompt = (
        "Explain why this finding was flagged in 2-4 concise bullet points. "
        "Reference evidence fields and risk impact. Return plain text only."
    )
    response = await call(
        "smart",
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": finding.model_dump_json()},
        ],
        cacheable=False,
        stream=False,
    )
    return str(response).strip() if isinstance(response, str) else ""


def _is_placeholder_reasoning(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return True
    return any(snippet in normalized for snippet in _PLACEHOLDER_REASONING_SNIPPETS)


def _trim_mention_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("<@") and ">" in stripped:
        return stripped.split(">", 1)[1].strip()
    return stripped


def _top_findings_brief(findings: list[Finding], limit: int = 8) -> list[dict[str, str]]:
    ranked = sorted(
        findings,
        key=lambda finding: finding.created_at,
        reverse=True,
    )
    return [
        {
            "id": finding.id,
            "severity": finding.severity,
            "title": finding.title,
            "summary": finding.summary,
        }
        for finding in ranked[:limit]
    ]


def _deterministic_cfo_fallback(question: str, findings: list[Finding]) -> str:
    if not findings:
        return "No new findings were detected in the last 24 hours."
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    top = max(findings, key=lambda finding: severity_rank.get(finding.severity, 0))
    if "urgent" in question.lower():
        return (
            f"Most urgent finding: [{top.severity.upper()}] {top.title}. "
            f"{top.summary} (id: {top.id})"
        )
    return (
        f"Top finding right now is [{top.severity.upper()}] {top.title}. "
        f"{top.summary} (id: {top.id})"
    )


async def _stream_cfo_reply(channel: str, question: str) -> None:
    recent_findings = await get_recent_findings(hours=24)
    compact = _top_findings_brief(recent_findings)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Vellum's CFO assistant in Slack. Answer in under 120 words, "
                "prioritize urgency, include severity + finding id when available, and stay concise."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Recent findings (last 24h): {compact}"
            ),
        },
    ]
    try:
        token_stream = await call(
            "fast",
            messages,
            cacheable=False,
            stream=True,
        )
        await stream_to_slack(
            channel=channel,
            generator=token_stream,
            initial_text="Analyzing today's findings...",
        )
    except Exception as exc:
        logger.info("slack.cfo_chat_fallback", error=str(exc))
        fallback = _deterministic_cfo_fallback(question, recent_findings)
        client = _web_client()
        await client.chat_postMessage(channel=channel, text=fallback)


def build_slack_app(settings: VellumSettings) -> AsyncApp:
    """Create a Slack Bolt async app configured for Socket Mode."""
    app = AsyncApp(token=settings.slack_bot_token)

    @app.event("app_mention")
    async def handle_app_mention(event: dict[str, Any]) -> None:
        text = _trim_mention_text(str(event.get("text", "")))
        channel = str(event.get("channel", ""))
        if channel and text:
            await _stream_cfo_reply(channel, text)

    @app.event("message")
    async def handle_dm_message(event: dict[str, Any]) -> None:
        if event.get("channel_type") != "im":
            return
        if event.get("subtype") is not None:
            return
        if event.get("bot_id"):
            return
        text = str(event.get("text", "")).strip()
        channel = str(event.get("channel", ""))
        if channel and text:
            await _stream_cfo_reply(channel, text)

    @app.command("/audit")
    async def handle_audit_command(ack, body: dict[str, Any], respond) -> None:
        await ack()
        await respond(text="Generating audit pack...")
        period = _extract_period(body.get("text"))
        try:
            result = await _forward_json(settings, f"/audit/{period}", {})
            gdoc_url = result.get("gdoc_url") or result.get("url") or "No URL returned."
            await respond(replace_original=True, text=f"Audit pack ready: {gdoc_url}")
        except httpx.HTTPError as exc:
            logger.info("slack.audit_forward_failed", error=str(exc), period=period)
            await respond(replace_original=True, text="Failed to generate audit pack.")

    @app.action("approve_finding")
    async def handle_approve_action(ack, body: dict[str, Any], client: AsyncWebClient) -> None:
        await ack()
        actions = body.get("actions", [])
        finding_id = str(actions[0].get("value")) if actions else ""
        user_id = str(body.get("user", {}).get("id", ""))
        try:
            await _forward_json(
                settings,
                f"/findings/{finding_id}/decision",
                {
                    "decision": "approve",
                    "user": user_id,
                },
            )
            message = body.get("message", {})
            channel = body.get("channel", {}).get("id")
            if channel and message.get("ts"):
                await client.chat_update(
                    channel=str(channel),
                    ts=str(message["ts"]),
                    text=f"APPROVED: {finding_id}",
                    blocks=_decision_blocks(list(message.get("blocks", [])), "approve", user_id),
                )
        except httpx.HTTPError as exc:
            logger.info("slack.approve_forward_failed", error=str(exc), finding_id=finding_id)

    @app.action("reject_finding")
    async def handle_reject_action(ack, body: dict[str, Any], client: AsyncWebClient) -> None:
        await ack()
        actions = body.get("actions", [])
        finding_id = str(actions[0].get("value")) if actions else ""
        user_id = str(body.get("user", {}).get("id", ""))
        try:
            await _forward_json(
                settings,
                f"/findings/{finding_id}/decision",
                {
                    "decision": "reject",
                    "user": user_id,
                },
            )
            message = body.get("message", {})
            channel = body.get("channel", {}).get("id")
            if channel and message.get("ts"):
                await client.chat_update(
                    channel=str(channel),
                    ts=str(message["ts"]),
                    text=f"REJECTED: {finding_id}",
                    blocks=_decision_blocks(list(message.get("blocks", [])), "reject", user_id),
                )
        except httpx.HTTPError as exc:
            logger.info("slack.reject_forward_failed", error=str(exc), finding_id=finding_id)

    @app.action("why_finding")
    async def handle_why_action(ack, body: dict[str, Any], client: AsyncWebClient) -> None:
        await ack()
        actions = body.get("actions", [])
        finding_id = str(actions[0].get("value")) if actions else ""
        user_id = str(body.get("user", {}).get("id", ""))
        channel = str(body.get("channel", {}).get("id", ""))
        findings = await get_findings(filters={"id": finding_id, "limit": 1})
        if not findings:
            text = f"No reasoning available for `{finding_id}`."
        else:
            finding = findings[0]
            reasoning = finding.reasoning_trace.strip()
            if _is_placeholder_reasoning(reasoning):
                try:
                    reasoning = await _llm_reasoning_trace(finding)
                except Exception as exc:
                    logger.info("slack.why_llm_failed", finding_id=finding.id, error=str(exc))
            if reasoning:
                if reasoning != finding.reasoning_trace:
                    await write_finding(finding.model_copy(update={"reasoning_trace": reasoning}))
                text = reasoning
            else:
                text = "Reasoning trace is not available yet for this finding."
        if channel and user_id:
            await client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                text=f"*Why?* {text}",
            )

    return app


async def start_socket_mode(app: AsyncApp, settings: VellumSettings) -> None:
    """Start the Slack Socket Mode handler."""
    handler = AsyncSocketModeHandler(app, settings.slack_app_token)
    await handler.start_async()


async def post_finding_card(finding: Finding) -> str:
    """Post a Block Kit finding card and persist the resulting message ts."""
    settings = get_settings()
    client = _web_client()
    severity_emoji = _SEVERITY_EMOJI.get(finding.severity, ":white_circle:")
    evidence_count = len(finding.evidence)
    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{severity_emoji} *{finding.title}*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": finding.summary},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*Severity:* {finding.severity}"},
                {"type": "mrkdwn", "text": f"*Evidence count:* {evidence_count}"},
            ],
        },
    ]
    actions: list[dict[str, Any]] = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Why?"},
            "action_id": "why_finding",
            "value": finding.id,
        }
    ]
    if _requires_approval(finding):
        actions.extend(
            [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "action_id": "approve_finding",
                    "value": finding.id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "action_id": "reject_finding",
                    "value": finding.id,
                },
            ]
        )
    blocks.append({"type": "actions", "elements": actions})

    response = await client.chat_postMessage(
        channel=settings.slack_finance_alerts_channel,
        text=f"{finding.severity.upper()}: {finding.title}",
        blocks=blocks,
    )
    message_ts = str(response["ts"])
    await write_finding(finding)
    await write_slack_message_ts(finding.id, message_ts)
    return message_ts

