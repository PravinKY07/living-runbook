"""SQLite storage for runbook drafts, versions, and approval state."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from app.models.runbook import RunbookDraft, RunbookMetadata, RunbookStatus
from app.security.runbook_scan import require_safe_runbook


class RunbookNotFoundError(LookupError):
    """Raised when a runbook or version does not exist."""


class RunbookApprovalError(PermissionError):
    """Raised when an approval or publication rule is not satisfied."""


@dataclass(frozen=True, slots=True)
class StoredRunbook:
    """A runbook identifier with its current draft."""

    runbook_id: str
    draft: RunbookDraft


class SQLiteRunbookStore:
    """Persist only scanned Markdown and non-sensitive metadata."""

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
        """Create runbook tables if they do not exist."""
        with self._lock:
            connection = self._connect()
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runbooks (
                    id TEXT PRIMARY KEY,
                    repository_url TEXT,
                    repository_commit TEXT,
                    provider TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runbook_versions (
                    runbook_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_by INTEGER,
                    approved_at TEXT,
                    PRIMARY KEY (runbook_id, version),
                    FOREIGN KEY (runbook_id) REFERENCES runbooks(id)
                );
                """
            )
            connection.commit()

    def create_draft(self, draft: RunbookDraft) -> StoredRunbook:
        """Store a scanned runbook as version one in draft status."""
        require_safe_runbook(draft.content)
        with self._lock:
            self.initialize()
            runbook_id = uuid.uuid4().hex
            metadata = draft.metadata
            connection = self._connect()
            connection.execute(
                """
                INSERT INTO runbooks (
                    id, repository_url, repository_commit, provider,
                    current_version, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    runbook_id,
                    metadata.repository_url,
                    metadata.repository_commit,
                    metadata.provider,
                    metadata.version,
                    "draft",
                    _timestamp(metadata.created_at),
                ),
            )
            self._insert_version(connection, runbook_id, draft)
            connection.commit()
            return StoredRunbook(runbook_id=runbook_id, draft=draft)

    def get(self, runbook_id: str) -> StoredRunbook:
        """Return the current runbook version."""
        with self._lock:
            self.initialize()
            row = self._connect().execute(
                "SELECT current_version FROM runbooks WHERE id = ?",
                (runbook_id,),
            ).fetchone()
            if row is None:
                raise RunbookNotFoundError("Runbook not found.")
            return StoredRunbook(
                runbook_id=runbook_id,
                draft=self._draft_for_version(runbook_id, row["current_version"]),
            )

    def list_versions(self, runbook_id: str) -> tuple[RunbookDraft, ...]:
        """Return all stored versions ordered from newest to oldest."""
        with self._lock:
            self.initialize()
            rows = self._connect().execute(
                """
                SELECT version FROM runbook_versions
                WHERE runbook_id = ?
                ORDER BY version DESC
                """,
                (runbook_id,),
            ).fetchall()
            if not rows:
                raise RunbookNotFoundError("Runbook not found.")
            return tuple(
                self._draft_for_version(runbook_id, row["version"])
                for row in rows
            )

    def approve(self, runbook_id: str, *, approver_id: int, role: str) -> StoredRunbook:
        """Approve the current draft when called by an Approver."""
        if role != "approver":
            raise RunbookApprovalError("Only an Approver can approve a runbook.")
        with self._lock:
            current = self.get(runbook_id)
            if current.draft.metadata.status != "draft":
                raise RunbookApprovalError("Only a draft can be approved.")
            approved_at = datetime.now(UTC)
            draft = current.draft.model_copy(
                update={
                    "metadata": current.draft.metadata.model_copy(
                        update={
                            "status": "approved",
                            "approved_by": approver_id,
                            "approved_at": approved_at,
                        }
                    )
                }
            )
            self._update_version_status(runbook_id, draft, "approved")
            self._update_runbook_status(runbook_id, "approved")
            return StoredRunbook(runbook_id=runbook_id, draft=draft)

    def publish(self, runbook_id: str, *, role: str) -> StoredRunbook:
        """Publish an approved runbook when called by an Approver."""
        if role != "approver":
            raise RunbookApprovalError("Only an Approver can publish a runbook.")
        with self._lock:
            current = self.get(runbook_id)
            if current.draft.metadata.status != "approved":
                raise RunbookApprovalError("Only an approved runbook can be published.")
            draft = current.draft.model_copy(
                update={"metadata": current.draft.metadata.model_copy(update={"status": "published"})}
            )
            self._update_version_status(runbook_id, draft, "published")
            self._update_runbook_status(runbook_id, "published")
            return StoredRunbook(runbook_id=runbook_id, draft=draft)

    def _insert_version(
        self,
        connection: sqlite3.Connection,
        runbook_id: str,
        draft: RunbookDraft,
    ) -> None:
        metadata = draft.metadata
        connection.execute(
            """
            INSERT INTO runbook_versions (
                runbook_id, version, content, content_hash, provider,
                prompt_version, status, created_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                runbook_id,
                metadata.version,
                draft.content,
                metadata.content_hash,
                metadata.provider,
                metadata.prompt_version,
                metadata.status,
                _timestamp(metadata.created_at),
                metadata.approved_by,
                _timestamp(metadata.approved_at) if metadata.approved_at else None,
            ),
        )

    def _draft_for_version(self, runbook_id: str, version: int) -> RunbookDraft:
        row = self._connect().execute(
            """
            SELECT content, content_hash, provider, prompt_version, status,
                   created_at, approved_by, approved_at
            FROM runbook_versions
            WHERE runbook_id = ? AND version = ?
            """,
            (runbook_id, version),
        ).fetchone()
        if row is None:
            raise RunbookNotFoundError("Runbook version not found.")
        content = row["content"]
        actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual_hash != row["content_hash"]:
            raise RunbookApprovalError("Stored runbook content failed its hash check.")
        return RunbookDraft(
            content=content,
            metadata=RunbookMetadata(
                version=version,
                repository_url=self._runbook_value(runbook_id, "repository_url"),
                repository_commit=self._runbook_value(runbook_id, "repository_commit"),
                provider=row["provider"],
                prompt_version=row["prompt_version"],
                content_hash=row["content_hash"],
                status=row["status"],
                created_at=row["created_at"],
                approved_by=row["approved_by"],
                approved_at=row["approved_at"],
            ),
        )

    def _runbook_value(self, runbook_id: str, column: str) -> str | None:
        row = self._connect().execute(
            f"SELECT {column} FROM runbooks WHERE id = ?",
            (runbook_id,),
        ).fetchone()
        if row is None:
            raise RunbookNotFoundError("Runbook not found.")
        return row[column]

    def _update_version_status(
        self,
        runbook_id: str,
        draft: RunbookDraft,
        status: RunbookStatus,
    ) -> None:
        metadata = draft.metadata
        connection = self._connect()
        connection.execute(
            """
            UPDATE runbook_versions
            SET status = ?, approved_by = ?, approved_at = ?
            WHERE runbook_id = ? AND version = ?
            """,
            (
                status,
                metadata.approved_by,
                _timestamp(metadata.approved_at) if metadata.approved_at else None,
                runbook_id,
                metadata.version,
            ),
        )
        connection.commit()

    def _update_runbook_status(self, runbook_id: str, status: RunbookStatus) -> None:
        connection = self._connect()
        connection.execute(
            "UPDATE runbooks SET status = ? WHERE id = ?",
            (status, runbook_id),
        )
        connection.commit()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
