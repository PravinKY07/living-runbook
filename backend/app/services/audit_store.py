"""SQLite audit events for security-relevant actions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock


class SQLiteAuditStore:
    """Store non-sensitive audit metadata without raw source or secrets."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            if self._database_path != ":memory:":
                Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                self._database_path,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def initialize(self) -> None:
        """Create the audit table if it does not exist."""
        with self._lock:
            self._connect().execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor_id INTEGER,
                    resource_id TEXT,
                    outcome TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._connect().commit()

    def record(
        self,
        *,
        event_type: str,
        outcome: str,
        actor_id: int | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record a bounded, non-sensitive audit event."""
        safe_metadata = json.dumps(metadata or {}, separators=(",", ":"))
        if len(safe_metadata) > 2000:
            safe_metadata = json.dumps({"truncated": True}, separators=(",", ":"))
        with self._lock:
            self.initialize()
            self._connect().execute(
                """
                INSERT INTO audit_events (
                    event_type, actor_id, resource_id, outcome,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    actor_id,
                    resource_id,
                    outcome,
                    safe_metadata,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._connect().commit()

    def list_for_resource(self, resource_id: str) -> tuple[dict, ...]:
        """Return safe audit metadata for a resource."""
        with self._lock:
            self.initialize()
            rows = self._connect().execute(
                """
                SELECT event_type, actor_id, resource_id, outcome, metadata_json, created_at
                FROM audit_events
                WHERE resource_id = ?
                ORDER BY id
                """,
                (resource_id,),
            ).fetchall()
            return tuple(dict(row) for row in rows)

    def list_recent(self, limit: int = 100) -> tuple[dict, ...]:
        """Return the most recent audit events, newest first.

        ``limit`` is capped at 100 to prevent unbounded reads.
        """
        safe_limit = min(max(1, limit), 100)
        with self._lock:
            self.initialize()
            rows = self._connect().execute(
                """
                SELECT event_type, actor_id, resource_id, outcome, metadata_json, created_at
                FROM audit_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            return tuple(dict(row) for row in rows)
