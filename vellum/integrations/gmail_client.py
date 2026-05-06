"""Async Gmail integration wrapper."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from vellum.integrations.google_auth import get_google_service


def _header_value(headers: list[dict[str, str]], name: str) -> str:
    name_lower = name.lower()
    for header in headers:
        if str(header.get("name", "")).lower() == name_lower:
            return str(header.get("value", ""))
    return ""


def _decode_body(data: str) -> str:
    if not data:
        return ""
    decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return decoded.decode("utf-8", errors="replace")


def _extract_plain_text(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType")
    body_data = str(payload.get("body", {}).get("data", ""))
    if mime_type == "text/plain" and body_data:
        return _decode_body(body_data)

    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text:
            return text
    if body_data:
        return _decode_body(body_data)
    return ""


async def search_recent(query: str, max_results: int = 20) -> list[dict]:
    """Search recent Gmail messages and return normalized metadata records."""
    service = await get_google_service("gmail", "v1")
    listed = await asyncio.to_thread(
        service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
        ).execute
    )
    messages = listed.get("messages", [])
    results: list[dict] = []
    for message in messages:
        message_id = str(message.get("id", ""))
        if not message_id:
            continue
        full = await asyncio.to_thread(
            service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute
        )
        payload = dict(full.get("payload", {}))
        headers = list(payload.get("headers", []))
        internal_date_ms = int(full.get("internalDate", 0) or 0)
        received_at = (
            datetime.fromtimestamp(internal_date_ms / 1000, tz=UTC).isoformat()
            if internal_date_ms
            else ""
        )
        if not received_at:
            date_header = _header_value(headers, "Date")
            if date_header:
                parsed = parsedate_to_datetime(date_header)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                received_at = parsed.astimezone(UTC).isoformat()
        results.append(
            {
                "id": message_id,
                "from_address": _header_value(headers, "From"),
                "to": _header_value(headers, "To"),
                "subject": _header_value(headers, "Subject"),
                "body": _extract_plain_text(payload),
                "received_at": received_at,
            }
        )
    return results


async def fetch_vendor_emails() -> list[dict]:
    """Fetch vendor-related email metadata for fraud checks."""
    return await search_recent(
        query='("update bank" OR "new wire" OR "change account") newer_than:30d',
        max_results=20,
    )

