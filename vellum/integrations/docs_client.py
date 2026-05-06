"""Async Google Docs integration wrapper."""

from __future__ import annotations

import asyncio

from vellum.integrations.google_auth import get_google_service


def _markdown_to_requests(body_markdown: str) -> list[dict]:
    lines = body_markdown.splitlines()
    plain_lines: list[str] = []
    heading_ranges: list[tuple[int, int, str]] = []
    bullet_ranges: list[tuple[int, int]] = []
    cursor = 1

    for raw_line in lines:
        stripped = raw_line.strip()
        style = ""
        is_bullet = False
        text = raw_line
        if stripped.startswith("### "):
            style = "HEADING_3"
            text = stripped[4:]
        elif stripped.startswith("## "):
            style = "HEADING_2"
            text = stripped[3:]
        elif stripped.startswith("# "):
            style = "HEADING_1"
            text = stripped[2:]
        elif stripped.startswith("- "):
            is_bullet = True
            text = stripped[2:]
        plain_lines.append(text)
        start = cursor
        end = start + len(text)
        if style:
            heading_ranges.append((start, end, style))
        if is_bullet:
            bullet_ranges.append((start, end))
        cursor = end + 1

    plain_text = "\n".join(plain_lines)
    if plain_text:
        plain_text += "\n"

    requests: list[dict] = [{"insertText": {"location": {"index": 1}, "text": plain_text}}]
    for start, end, style in heading_ranges:
        requests.append(
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": style},
                    "fields": "namedStyleType",
                }
            }
        )
    for start, end in bullet_ranges:
        requests.append(
            {
                "createParagraphBullets": {
                    "range": {"startIndex": start, "endIndex": end},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            }
        )
    return requests


async def create_doc_from_template(title: str, body_markdown: str) -> str:
    """Create a Google Doc from markdown-like text and return the doc URL."""
    service = await get_google_service("docs", "v1")
    created = await asyncio.to_thread(
        service.documents().create(
            body={"title": title},
        ).execute
    )
    doc_id = str(created.get("documentId", ""))
    requests = _markdown_to_requests(body_markdown)
    if requests:
        await asyncio.to_thread(
            service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute
        )
    return f"https://docs.google.com/document/d/{doc_id}/edit"


async def create_audit_doc(title: str, body: str) -> str:
    """Create a Google Doc and return its URL."""
    return await create_doc_from_template(title=title, body_markdown=body)

