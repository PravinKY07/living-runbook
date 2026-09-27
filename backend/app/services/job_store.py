"""SQLite persistence for analysis job status."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from app.models.jobs import AnalysisJob, JobStatus


class JobNotFoundError(LookupError):
    """Raised when an analysis job does not exist."""


class _Unset:
    """Sentinel marking an update argument the caller did not supply."""


_UNSET = _Unset()


class SQLiteJobStore:
    """Persist job state so the UI can safely show progress and failures."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        with self._lock:
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
        """Create the jobs table if it does not exist."""
        with self._lock:
            self._connect().execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id TEXT PRIMARY KEY,
                    repository_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    runbook_id TEXT,
                    error_message TEXT
                )
                """
            )
            self._connect().commit()

    def create(self, repository_url: str) -> AnalysisJob:
        """Create a queued job."""
        with self._lock:
            self.initialize()
            job_id = uuid.uuid4().hex
            now = _timestamp(datetime.now(UTC))
            self._connect().execute(
                """
                INSERT INTO analysis_jobs (
                    id, repository_url, status, created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?)
                """,
                (job_id, repository_url, now, now),
            )
            self._connect().commit()
            return AnalysisJob(
                id=job_id,
                repository_url=repository_url,
                status="queued",
                created_at=now,
                updated_at=now,
            )

    def get(self, job_id: str) -> AnalysisJob:
        """Return a job by ID."""
        with self._lock:
            self.initialize()
            row = self._connect().execute(
                "SELECT * FROM analysis_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobNotFoundError("Analysis job not found.")
            return _job_from_row(row)

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        runbook_id: str | None | _Unset = _UNSET,
        error_message: str | None | _Unset = _UNSET,
    ) -> AnalysisJob:
        """Update a job status, preserving fields the caller did not supply.

        Omitting runbook_id or error_message leaves the stored value alone, so a
        partial status update cannot silently erase a result or an error.
        """
        with self._lock:
            current = self.get(job_id)
            updated = current.model_copy(
                update={
                    "status": status,
                    "updated_at": datetime.now(UTC),
                    "runbook_id": current.runbook_id if isinstance(runbook_id, _Unset) else runbook_id,
                    "error_message": (
                        current.error_message
                        if isinstance(error_message, _Unset)
                        else error_message
                    ),
                }
            )
            self._connect().execute(
                """
                UPDATE analysis_jobs
                SET status = ?, updated_at = ?, runbook_id = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    updated.status,
                    _timestamp(updated.updated_at),
                    updated.runbook_id,
                    updated.error_message,
                    job_id,
                ),
            )
            self._connect().commit()
            return updated


def _job_from_row(row: sqlite3.Row) -> AnalysisJob:
    return AnalysisJob(
        id=row["id"],
        repository_url=row["repository_url"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        runbook_id=row["runbook_id"],
        error_message=row["error_message"],
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
