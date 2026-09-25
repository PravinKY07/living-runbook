from concurrent.futures import Future
from pathlib import Path

from app.security.url_policy import validate_github_repository_url
from app.services.analysis_jobs import AnalysisJobManager
from app.services.job_store import SQLiteJobStore
from app.services.repository_loader import LoadedRepository
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
