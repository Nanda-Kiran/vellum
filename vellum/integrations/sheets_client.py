"""Async Google Sheets integration wrapper."""

from __future__ import annotations

import asyncio

from vellum.integrations.google_auth import get_google_service
from vellum.settings import get_settings


async def read_range(spreadsheet_id: str, range_a1: str) -> list[list[str]]:
    """Read a range from Google Sheets and return rows of string values."""
    service = await get_google_service("sheets", "v4")
    response = await asyncio.to_thread(
        service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
        ).execute
    )
    values = response.get("values", [])
    return [[str(cell) for cell in row] for row in values]


async def append_row(spreadsheet_id: str, range_a1: str, row: list) -> None:
    """Append one row to a sheet range."""
    service = await get_google_service("sheets", "v4")
    await asyncio.to_thread(
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute
    )


async def fetch_expense_rows() -> list[dict]:
    """Fetch expense rows from policy-relevant Google Sheets."""
    settings = get_settings()
    if not settings.demo_sheet_id:
        return []
    rows = await read_range(settings.demo_sheet_id, settings.demo_sheet_range)
    if not rows:
        return []

    first_row = [cell.strip().lower() for cell in rows[0]]
    expected_headers = ["date", "category", "description", "amount", "submitter"]
    start_index = 1 if all(header in first_row for header in expected_headers) else 0
    parsed: list[dict] = []
    for row in rows[start_index:]:
        if not row:
            continue
        row_values = [str(value) for value in row]
        while len(row_values) < 5:
            row_values.append("")
        parsed.append(
            {
                "date": row_values[0],
                "category": row_values[1],
                "description": row_values[2],
                "amount": row_values[3],
                "submitter": row_values[4],
            }
        )
    return parsed

