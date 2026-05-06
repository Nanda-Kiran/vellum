"""Seed script for policy-violating expense rows."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from vellum.integrations.sheets_client import append_row
from vellum.integrations.google_auth import get_google_service
from vellum.settings import get_settings


async def _create_demo_sheet_with_headers() -> tuple[str, str]:
    """Create a demo spreadsheet and seed header row."""
    service = await get_google_service("sheets", "v4")
    created = await asyncio.to_thread(
        service.spreadsheets().create(
            body={
                "properties": {"title": "Vellum Demo Expenses"},
                "sheets": [{"properties": {"title": "Sheet1"}}],
            },
            fields="spreadsheetId,spreadsheetUrl",
        ).execute
    )
    spreadsheet_id = str(created.get("spreadsheetId", ""))
    spreadsheet_url = str(created.get("spreadsheetUrl", ""))
    await asyncio.to_thread(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1:E1",
            valueInputOption="RAW",
            body={
                "values": [
                    ["date", "category", "description", "amount", "submitter"],
                ]
            },
        ).execute
    )
    return spreadsheet_id, spreadsheet_url


async def seed_policy_violating_dinner() -> None:
    """Append an $890 dinner expense row to the demo Sheet.

    If DEMO_SHEET_ID is unset, creates a new sheet with required headers.
    """
    settings = get_settings()
    spreadsheet_id = settings.demo_sheet_id
    target_range = settings.demo_sheet_range
    created_sheet_url = ""
    if not spreadsheet_id:
        spreadsheet_id, created_sheet_url = await _create_demo_sheet_with_headers()
        target_range = "Sheet1!A:E"

    row = [
        datetime.now(UTC).date().isoformat(),
        "meal",
        "NYC client dinner, 2 attendees",
        "890",
        "demo@vellum.test",
    ]
    await append_row(spreadsheet_id, target_range, row)
    print(
        "✓ planted: policy-violating sheet row "
        "(meal | NYC client dinner, 2 attendees | amount=890 | submitter=demo@vellum.test)."
    )
    if created_sheet_url:
        print(f"✓ planted: created demo sheet {created_sheet_url}")
        print(
            "Set these in .env for future runs:\n"
            f"DEMO_SHEET_ID={spreadsheet_id}\n"
            "DEMO_SHEET_RANGE=Sheet1!A:E"
        )


if __name__ == "__main__":
    asyncio.run(seed_policy_violating_dinner())

