from concurrent.futures import Future
from pathlib import Path

from app.security.url_policy import validate_github_repository_url
from app.services.analysis_jobs import AnalysisJobManager
from app.services.audit_store import SQLiteAuditStore
from app.services.job_store import SQLiteJobStore
from app.services.repository_loader import LoadedRepository, RepositoryCleanupError
from app.services.runbook_store import SQLiteRunbookStore
from app.services.safe_manifest import build_safe_manifest


class InlineExecutor:
    """Test executor that runs work immediately in the calling thread."""

    def submit(self, function, *args, **kwargs):
        future = Future()
        future.set_result(function(*args, **kwargs))
        return future


class FakeLoader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, url: str):
        manifest = build_safe_manifest(self.root, repository_commit="abc1234")
        return _FakeContext(
            LoadedRepository(
                repository=validate_github_repository_url(url),
                root=self.root,
                manifest=manifest,
            )
        )


class _FakeContext:
    def __init__(self, loaded: LoadedRepository) -> None:
        self.loaded = loaded

    def __enter__(self) -> LoadedRepository:
        return self.loaded

    def __exit__(self, *args) -> None:
        return None


def make_fixture(root: Path) -> None:
    (root / "app.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'ok'}\n",
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text("fastapi>=0.100.0\n", encoding="utf-8")


def make_manager(tmp_path: Path) -> AnalysisJobManager:
    make_fixture(tmp_path)
    database_path = str(tmp_path / "jobs.db")
    return AnalysisJobManager(
        job_store=SQLiteJobStore(database_path),
        runbook_store=SQLiteRunbookStore(database_path),
        audit_store=SQLiteAuditStore(database_path),
        loader=FakeLoader(tmp_path),
        executor=InlineExecutor(),
    )


def test_job_runs_static_analysis_and_creates_runbook(tmp_path):
    manager = make_manager(tmp_path)

    job = manager.submit("https://github.com/example/project")
    manager.wait(job.id)

    completed = manager.get(job.id)
    assert completed.status == "completed"
    assert completed.runbook_id is not None
    events = manager._audit_store.list_for_resource(job.id)
    assert [event["event_type"] for event in events] == [
        "analysis_submitted",
        "analysis_started",
        "analysis_completed",
    ]


def test_failed_job_returns_safe_error(tmp_path):
    make_fixture(tmp_path)
    database_path = str(tmp_path / "jobs.db")
    manager = AnalysisJobManager(
        job_store=SQLiteJobStore(database_path),
        runbook_store=SQLiteRunbookStore(database_path),
        loader=FailingLoader(),
        executor=InlineExecutor(),
    )

    job = manager.submit("https://github.com/example/project")
    manager.wait(job.id)

    failed = manager.get(job.id)
    assert failed.status == "failed"
    assert failed.error_message == "Repository analysis failed safely."


class FailingLoader:
    def load(self, url: str):
        from app.services.repository_loader import RepositoryLoadError

        raise RepositoryLoadError("Repository clone failed safely.")


class OverLimitLoader:
    def load(self, url: str):
        from app.services.safe_manifest import RepositoryLimitError

        raise RepositoryLimitError("Repository exceeds the allowed file count.")


def test_oversized_repository_reaches_a_terminal_status(tmp_path):
    """A limit breach must not escape the worker and strand the job in running."""
    database_path = str(tmp_path / "jobs.db")
    manager = AnalysisJobManager(
        job_store=SQLiteJobStore(database_path),
        runbook_store=SQLiteRunbookStore(database_path),
        audit_store=SQLiteAuditStore(database_path),
        loader=OverLimitLoader(),
        executor=InlineExecutor(),
    )

    job = manager.submit("https://github.com/example/project")
    manager.wait(job.id)

    failed = manager.get(job.id)
    assert failed.status == "failed"
    assert "larger than this demo can analyze" in (failed.error_message or "")
    events = manager._audit_store.list_for_resource(job.id)
    assert [event["event_type"] for event in events] == [
        "analysis_submitted",
        "analysis_started",
        "analysis_failed",
    ]


class CleanupFailingLoader(FakeLoader):
    def load(self, url: str):
        return _CleanupFailingContext(super().load(url))


class _CleanupFailingContext:
    def __init__(self, context) -> None:
        self._context = context

    def __enter__(self):
        return self._context.__enter__()

    def __exit__(self, *args):
        raise RepositoryCleanupError("Temporary repository workspace could not be removed.")


def test_cleanup_failure_is_audited(tmp_path):
    make_fixture(tmp_path)
    database_path = str(tmp_path / "jobs.db")
    manager = AnalysisJobManager(
        job_store=SQLiteJobStore(database_path),
        runbook_store=SQLiteRunbookStore(database_path),
        audit_store=SQLiteAuditStore(database_path),
        loader=CleanupFailingLoader(tmp_path),
        executor=InlineExecutor(),
    )

    job = manager.submit("https://github.com/example/project")
    manager.wait(job.id)

    failed = manager.get(job.id)
    assert failed.status == "failed"
    assert "cleanup" in failed.error_message
    assert any(
        event["event_type"] == "repository_cleanup_failed"
        for event in manager._audit_store.list_for_resource(job.id)
    )


def test_well_formed_manifest_with_unexpected_shape_reaches_a_terminal_status(tmp_path):
    """A public repository is untrusted input.

    "dependencies": [] in a package.json is valid JSON. Before the analyzer
    validated shapes, it raised AttributeError, which was absent from the
    worker's except tuple: the thread died, the job stayed "running" forever,
    and the browser polled indefinitely. Any exception type missing from that
    tuple produces the same failure, so the test asserts the terminal status
    rather than the absence of a crash.
    """
    (tmp_path / "package.json").write_text('{"name": "demo", "dependencies": []}\n', encoding="utf-8")
    database_path = str(tmp_path / "jobs.db")
    manager = AnalysisJobManager(
        job_store=SQLiteJobStore(database_path),
        runbook_store=SQLiteRunbookStore(database_path),
        audit_store=SQLiteAuditStore(database_path),
        loader=FakeLoader(tmp_path),
        executor=InlineExecutor(),
    )

    job = manager.submit("https://github.com/example/project")
    manager.wait(job.id)

    finished = manager.get(job.id)
    assert finished.status in {"completed", "failed"}
    assert finished.status != "running"


def test_completed_futures_are_released(tmp_path):
    """The job manager keeps futures for wait(); they must not accumulate."""
    make_fixture(tmp_path)
    database_path = str(tmp_path / "jobs.db")
    manager = AnalysisJobManager(
        job_store=SQLiteJobStore(database_path),
        runbook_store=SQLiteRunbookStore(database_path),
        audit_store=SQLiteAuditStore(database_path),
        loader=FakeLoader(tmp_path),
        executor=InlineExecutor(),
    )

    for _ in range(3):
        job = manager.submit("https://github.com/example/project")
        manager.wait(job.id)

    assert manager._futures == {}
