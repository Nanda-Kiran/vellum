"""SQLite trust ledger abstraction for all write operations."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
from sqlite_utils import Database

from vellum.contracts import Action, Finding, LedgerEntry
from vellum.logging_setup import get_logger
from vellum.settings import get_settings

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


class _AioSqlitePool:
    """Lightweight shared-connection manager for async SQLite access."""

    def __init__(self) -> None:
        self._connections: dict[str, aiosqlite.Connection] = {}
        self._lock = asyncio.Lock()

    async def get(self, db_path: str) -> aiosqlite.Connection:
        """Return or open a pooled connection for a database path."""
        async with self._lock:
            if db_path in self._connections:
                return self._connections[db_path]
            connection = await aiosqlite.connect(db_path)
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA journal_mode=WAL;")
            await connection.execute("PRAGMA synchronous=NORMAL;")
            await connection.commit()
            self._connections[db_path] = connection
            return connection

    async def close_all(self) -> None:
        """Close and clear all pooled SQLite connections."""
        async with self._lock:
            for connection in self._connections.values():
                await connection.close()
            self._connections.clear()


_POOL = _AioSqlitePool()


async def _ensure_schema(db_path: str) -> None:
    """Initialize all ledger tables and indexes using sqlite-utils."""

    def _create_schema() -> None:
        db = Database(db_path)
        db["findings"].create(
            {
                "id": str,
                "finding_json": str,
                "created_at": str,
                "severity": str,
                "agent": str,
                "status": str,
                "slack_message_ts": str,
            },
            pk="id",
            if_not_exists=True,
        )
        db["actions"].create(
            {
                "id": str,
                "finding_id": str,
                "action_json": str,
                "status": str,
                "approver": str,
                "executed_at": str,
            },
            pk="id",
            foreign_keys=(("finding_id", "findings", "id"),),
            if_not_exists=True,
        )
        db["audit_packs"].create(
            {
                "id": str,
                "period": str,
                "gdoc_url": str,
                "finding_ids": str,
                "created_at": str,
            },
            pk="id",
            if_not_exists=True,
        )
        db["eval_results"].create(
            {
                "id": str,
                "case_id": str,
                "passed": bool,
                "notes": str,
                "run_at": str,
            },
            pk="id",
            if_not_exists=True,
        )
        db["findings"].create_index(["created_at"], if_not_exists=True)
        db["findings"].create_index(["severity", "agent", "status"], if_not_exists=True)
        db["actions"].create_index(["finding_id", "status"], if_not_exists=True)
        db["audit_packs"].create_index(["period", "created_at"], if_not_exists=True)
        db["eval_results"].create_index(["case_id", "run_at"], if_not_exists=True)

        columns = set(db["findings"].columns_dict.keys())
        if "slack_message_ts" not in columns:
            db["findings"].add_column("slack_message_ts", str)

    await asyncio.to_thread(_create_schema)


def _resolve_db_path(explicit_db_path: str | Path | None = None) -> str:
    if explicit_db_path is not None:
        return str(explicit_db_path)
    return get_settings().vellum_db_path


async def _get_connection(db_path: str | Path | None = None) -> tuple[str, aiosqlite.Connection]:
    resolved = _resolve_db_path(db_path)
    await _ensure_schema(resolved)
    connection = await _POOL.get(resolved)
    return resolved, connection


async def write_finding(f: Finding, db_path: str | Path | None = None) -> None:
    """Persist a finding and its suggested actions."""
    _, connection = await _get_connection(db_path)
    await connection.execute(
        """
        INSERT OR REPLACE INTO findings (id, finding_json, created_at, severity, agent, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            f.id,
            f.model_dump_json(),
            f.created_at.isoformat(),
            f.severity,
            f.agent,
            "open",
        ),
    )
    for action in f.suggested_actions:
        await connection.execute(
            """
            INSERT OR REPLACE INTO actions (id, finding_id, action_json, status, approver, executed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                action.id,
                f.id,
                action.model_dump_json(),
                action.status,
                None,
                None,
            ),
        )
    await connection.commit()


async def get_findings(filters: dict[str, Any] | None = None, db_path: str | Path | None = None) -> list[Finding]:
    """Fetch findings with optional filters for severity, agent, status, or ids."""
    filters = filters or {}
    _, connection = await _get_connection(db_path)

    clauses: list[str] = []
    params: list[Any] = []

    if "id" in filters:
        clauses.append("id = ?")
        params.append(str(filters["id"]))
    if "severity" in filters:
        clauses.append("severity = ?")
        params.append(str(filters["severity"]))
    if "agent" in filters:
        clauses.append("agent = ?")
        params.append(str(filters["agent"]))
    if "status" in filters:
        clauses.append("status = ?")
        params.append(str(filters["status"]))

    sql = "SELECT finding_json FROM findings"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"
    if "limit" in filters:
        sql += " LIMIT ?"
        params.append(int(filters["limit"]))

    cursor = await connection.execute(sql, params)
    rows = await cursor.fetchall()
    return [Finding.model_validate_json(str(row["finding_json"])) for row in rows]


async def update_action_status(
    action_id: str,
    status: str,
    approver: str | None = None,
    executed_at: datetime | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Update status metadata for a persisted action record."""
    _, connection = await _get_connection(db_path)
    executed_value = executed_at.isoformat() if executed_at else None
    await connection.execute(
        """
        UPDATE actions
        SET status = ?, approver = COALESCE(?, approver), executed_at = COALESCE(?, executed_at)
        WHERE id = ?
        """,
        (status, approver, executed_value, action_id),
    )
    await connection.commit()


async def write_slack_message_ts(
    finding_id: str,
    message_ts: str,
    db_path: str | Path | None = None,
) -> None:
    """Persist Slack message timestamp for a finding card."""
    _, connection = await _get_connection(db_path)
    await connection.execute(
        """
        UPDATE findings
        SET slack_message_ts = ?
        WHERE id = ?
        """,
        (message_ts, finding_id),
    )
    await connection.commit()


async def write_audit_pack(
    period: str,
    gdoc_url: str,
    finding_ids: list[str],
    db_path: str | Path | None = None,
) -> str:
    """Persist metadata for a generated audit pack and return its id."""
    pack_id = f"audit_{uuid4().hex}"
    _, connection = await _get_connection(db_path)
    await connection.execute(
        """
        INSERT INTO audit_packs (id, period, gdoc_url, finding_ids, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            pack_id,
            period,
            gdoc_url,
            json.dumps(finding_ids),
            _utc_now_iso(),
        ),
    )
    await connection.commit()
    return pack_id


async def get_recent_findings(hours: int, db_path: str | Path | None = None) -> list[Finding]:
    """Return findings created within the last N hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    all_findings = await get_findings(db_path=db_path)
    return [finding for finding in all_findings if finding.created_at >= cutoff]


async def close_pool() -> None:
    """Close all pooled aiosqlite connections."""
    await _POOL.close_all()


class LedgerStore:
    """Async-friendly interface for persisting and reading ledger entries."""

    def __init__(self, db_path: str | Path) -> None:
        """Initialize a ledger store backed by SQLite."""
        self._db_path = str(db_path)

    async def initialize(self) -> None:
        """Create required tables and indexes for the ledger."""
        await _get_connection(self._db_path)

    async def append_entry(self, entry: LedgerEntry) -> None:
        """Append a new finding lifecycle entry to the ledger."""
        await write_finding(entry.finding, db_path=self._db_path)

    async def list_entries(self) -> list[LedgerEntry]:
        """Fetch ledger entries ordered by creation time."""
        findings = await get_findings(db_path=self._db_path)
        entries: list[LedgerEntry] = []
        _, connection = await _get_connection(self._db_path)
        for finding in findings:
            cursor = await connection.execute(
                """
                SELECT approver
                FROM actions
                WHERE finding_id = ?
                AND approver IS NOT NULL
                ORDER BY executed_at DESC
                LIMIT 1
                """,
                (finding.id,),
            )
            row = await cursor.fetchone()
            approver = str(row["approver"]) if row and row["approver"] else None
            finding_cursor = await connection.execute(
                """
                SELECT slack_message_ts
                FROM findings
                WHERE id = ?
                LIMIT 1
                """,
                (finding.id,),
            )
            finding_row = await finding_cursor.fetchone()
            slack_message_ts = (
                str(finding_row["slack_message_ts"])
                if finding_row and finding_row["slack_message_ts"]
                else None
            )
            entries.append(
                LedgerEntry(
                    finding=finding,
                    slack_message_ts=slack_message_ts,
                    approver=approver,
                    audit_pack_id=None,
                )
            )
        return entries

