"""Single in-process analysis job worker."""

from __future__ import annotations

import sqlite3
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from threading import RLock

from app.models.jobs import AnalysisJob
from app.security.evidence import EvidenceValidationError
from app.security.url_policy import validate_github_repository_url
from app.services.analysis_service import analyze_manifest
from app.services.audit_store import SQLiteAuditStore
from app.services.job_store import SQLiteJobStore
from app.services.repository_loader import (
    RepositoryCleanupError,
    RepositoryLoader,
    RepositoryLoadError,
)
from app.services.runbook_store import (
    RunbookApprovalError,
    RunbookIntegrityError,
    SQLiteRunbookStore,
)
from app.services.runbook_writer import RunbookWriter
from app.services.safe_manifest import RepositoryLimitError


class AnalysisJobManager:
    """Submit repository analysis without blocking the web request."""

    def __init__(
        self,
        *,
        job_store: SQLiteJobStore,
        runbook_store: SQLiteRunbookStore,
        audit_store: SQLiteAuditStore | None = None,
        loader: RepositoryLoader | None = None,
        writer: RunbookWriter | None = None,
        executor: Executor | None = None,
    ) -> None:
        self._job_store = job_store
        self._runbook_store = runbook_store
        self._audit_store = audit_store
        self._loader = loader or RepositoryLoader()
        self._writer = writer or RunbookWriter()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="living-runbook-analysis",
        )
        self._futures: dict[str, Future[None]] = {}
        self._lock = RLock()

    def submit(self, repository_url: str) -> AnalysisJob:
        """Validate the URL, persist a queued job, and start processing."""
        repository = validate_github_repository_url(repository_url)
        job = self._job_store.create(repository.normalized_url)
        self._audit("analysis_submitted", "success", resource_id=job.id)
        future = self._executor.submit(self._run, job.id, repository.normalized_url)
        with self._lock:
            self._futures[job.id] = future
        # Registered after insertion so the callback always finds its entry.
        # Without this the map grows for the lifetime of the process.
        future.add_done_callback(lambda _done: self._discard(job.id))
        return job

    def _discard(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    def wait(self, job_id: str, timeout: float | None = None) -> None:
        """Wait for a job in tests or controlled shutdown paths."""
        with self._lock:
            future = self._futures.get(job_id)
        if future is not None:
            future.result(timeout=timeout)

    def get(self, job_id: str) -> AnalysisJob:
        """Return current job status."""
        return self._job_store.get(job_id)

    def _run(self, job_id: str, repository_url: str) -> None:
        self._job_store.update(job_id, status="running")
        self._audit("analysis_started", "success", resource_id=job_id)
        try:
            with self._loader.load(repository_url) as loaded:
                analysis = analyze_manifest(
                    loaded.manifest,
                    repository_url=loaded.repository.normalized_url,
                )
                draft = self._writer.write(analysis)
                stored = self._runbook_store.create_draft(draft)
            self._job_store.update(
                job_id,
                status="completed",
                runbook_id=stored.runbook_id,
            )
            self._audit(
                "analysis_completed",
                "success",
                resource_id=job_id,
                metadata={"runbook_id": stored.runbook_id},
            )
        except RepositoryCleanupError:
            self._job_store.update(
                job_id,
                status="failed",
                error_message="Repository analysis failed and temporary cleanup needs attention.",
            )
            self._audit("repository_cleanup_failed", "failure", resource_id=job_id)
        except RepositoryLimitError:
            # A repository over the file-count or total-size ceiling is a normal
            # outcome, not a crash. It must still reach a terminal status or the
            # job would sit in "running" forever and the client would poll on.
            self._job_store.update(
                job_id,
                status="failed",
                error_message=(
                    "Repository is larger than this demo can analyze safely "
                    "(limit: 500 files or 10 MB). Try a smaller repository."
                ),
            )
            self._audit("analysis_failed", "failure", resource_id=job_id)
        except (
            EvidenceValidationError,
            RepositoryLoadError,
            RunbookApprovalError,
            RunbookIntegrityError,
            KeyError,
            IndexError,
            AttributeError,
            OSError,
            TypeError,
            ValueError,
            sqlite3.Error,
        ):
            # Kept deliberately broad. A repository is untrusted input, and an
            # exception type missing from this tuple does not fail the job, it
            # kills the worker thread and leaves the job polling forever.
            self._job_store.update(
                job_id,
                status="failed",
                error_message="Repository analysis failed safely.",
            )
            self._audit("analysis_failed", "failure", resource_id=job_id)

    def _audit(
        self,
        event_type: str,
        outcome: str,
        *,
        resource_id: str,
        metadata: dict | None = None,
    ) -> None:
        if self._audit_store is not None:
            self._audit_store.record(
                event_type=event_type,
                outcome=outcome,
                resource_id=resource_id,
                metadata=metadata,
            )
