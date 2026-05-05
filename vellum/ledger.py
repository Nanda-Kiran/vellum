"""SQLite trust ledger abstraction for all write operations."""

from __future__ import annotations

from pathlib import Path

from vellum.contracts import LedgerEntry


class LedgerStore:
    """Async-friendly interface for persisting and reading ledger entries."""

    def __init__(self, db_path: str | Path) -> None:
        """Initialize a ledger store backed by SQLite."""
        self._db_path = str(db_path)

    async def initialize(self) -> None:
        """Create required tables and indexes for the ledger."""
        raise NotImplementedError("TODO: Initialize SQLite schema in ledger.")

    async def append_entry(self, entry: LedgerEntry) -> None:
        """Append a new finding lifecycle entry to the ledger."""
        raise NotImplementedError("TODO: Persist ledger entry asynchronously.")

    async def list_entries(self) -> list[LedgerEntry]:
        """Fetch ledger entries ordered by creation time."""
        raise NotImplementedError("TODO: Read ledger entries asynchronously.")

