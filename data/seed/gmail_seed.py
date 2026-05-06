"""Seed script for vendor-fraud Gmail fixtures."""

from __future__ import annotations

import asyncio
import base64
from email.message import EmailMessage

from vellum.integrations.google_auth import get_google_service


async def seed_vendor_fraud_email() -> None:
    """Create (but do not send) a suspicious wire-update draft email."""
    service = await get_google_service("gmail", "v1")
    message = EmailMessage()
    message["To"] = "finance@vellum.test"
    message["From"] = "sarah.acme@personalmail.com"
    message["Subject"] = "Updated wire instructions"
    message.set_content(
        "Hi team,\n\n"
        "Please update Acme Corp's bank account to the following for all future invoices:\n"
        "Account number: 998877665544\n"
        "Routing number: 111000999\n\n"
        "Please confirm once completed.\n"
    )

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    draft = await asyncio.to_thread(
        service.users().drafts().create(
            userId="me",
            body={"message": {"raw": encoded}},
        ).execute
    )
    draft_id = str(draft.get("id", ""))
    print(
        "✓ planted: Gmail draft for wire-update fraud scenario "
        f"(draft id: {draft_id})."
    )
    print(
        "Instruction: open Gmail drafts, copy content into a personal mailbox email, "
        "send from the personal account to your demo finance inbox during the demo."
    )


if __name__ == "__main__":
    asyncio.run(seed_vendor_fraud_email())

