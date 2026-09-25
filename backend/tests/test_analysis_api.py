from concurrent.futures import Future
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security.url_policy import validate_github_repository_url
from app.services.analysis_jobs import AnalysisJobManager
from app.services.demo_seed import seed_demo_users
from app.services.job_store import SQLiteJobStore
from app.services.repository_loader import LoadedRepository
from app.services.runbook_store import SQLiteRunbookStore
from app.services.safe_manifest import build_safe_manifest
from app.services.user_store import SQLiteUserStore


class InlineExecutor:
    """Test executor that runs work immediately."""

    def submit(self, function, *args, **kwargs):
        future = Future()
        future.set_result(function(*args, **kwargs))
        return future


class FixtureLoader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, url: str):
        (self.root / "app.py").write_text(
            "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'ok'}\n\n@app.get('/orders')\ndef orders():\n    try:\n        return {'status': 'ok'}\n    except Exception:\n        return {'status': 'degraded'}\n",
            encoding="utf-8",
        )
        (self.root / "requirements.txt").write_text(
            "fastapi>=0.100.0\nuvicorn>=0.20.0\n",
            encoding="utf-8",
        )
        (self.root / "config.py").write_text(
            "import os\nDATABASE_URL = os.getenv('DATABASE_URL')\nREQUEST_TIMEOUT = os.getenv('REQUEST_TIMEOUT')\nFEATURE_FLAG = True\n",
            encoding="utf-8",
        )
        return FixtureContext(
            LoadedRepository(
                repository=validate_github_repository_url(url),
                root=self.root,
                manifest=build_safe_manifest(self.root, repository_commit="abc1234"),
            )
        )


class FixtureContext:
    def __init__(self, loaded: LoadedRepository) -> None:
        self.loaded = loaded

    def __enter__(self):
        return self.loaded

    def __exit__(self, *args):
        return None


def make_client(tmp_path: Path) -> TestClient:
    database_path = str(tmp_path / "app.db")
    settings = Settings(
        _env_file=None,
        database_path=database_path,
        session_secret="test-session-secret-that-is-long-enough",
        session_https_only=False,
    )
    user_store = SQLiteUserStore(database_path)
    seed_demo_users(
        user_store,
        editor_email="editor@example.test",
        editor_password="editor-test-password",
        approver_email="approver@example.test",
        approver_password="approver-test-password",
    )
    runbook_store = SQLiteRunbookStore(database_path)
    job_manager = AnalysisJobManager(
        job_store=SQLiteJobStore(database_path),
        runbook_store=runbook_store,
        loader=FixtureLoader(tmp_path / "fixture"),
        executor=InlineExecutor(),
    )
    (tmp_path / "fixture").mkdir(exist_ok=True)
    return TestClient(
        create_app(
            settings=settings,
            user_store=user_store,
            runbook_store=runbook_store,
            job_manager=job_manager,
        )
    )


def login(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_full_analysis_runbook_approval_flow(tmp_path):
    client = make_client(tmp_path)
    login(client, "editor@example.test", "editor-test-password")

    submitted = client.post(
        "/api/repositories/analyze",
        json={"repository_url": "https://github.com/example/project"},
    )
    assert submitted.status_code == 202
    job_id = submitted.json()["id"]

    job = client.get(f"/api/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    runbook_id = job.json()["runbook_id"]

    runbook = client.get(f"/api/runbooks/{runbook_id}")
    assert runbook.status_code == 200
    assert runbook.json()["metadata"]["provider"] == "static"
    assert "Entry points" in runbook.json()["content"]

    answer = client.post(
        f"/api/runbooks/{runbook_id}/ask",
        json={"question": "What failure modes were detected?"},
    )
    assert answer.status_code == 200
    assert answer.json()["provider"] == "static"
    assert answer.json()["citations"]
    assert "**" not in answer.json()["answer"]
    assert "No external calls" not in answer.json()["answer"]
    assert "Confirm the cited file" not in answer.json()["answer"]
    assert "Exception-handling path detected" in answer.json()["answer"]

    database_answer = client.post(
        f"/api/runbooks/{runbook_id}/ask",
        json={"question": "What happens when the database configuration is missing?"},
    )
    assert database_answer.status_code == 200
    assert "DATABASE_URL" in database_answer.json()["answer"]
    assert "REQUEST_TIMEOUT" not in database_answer.json()["answer"]
    assert "FEATURE_FLAG" not in database_answer.json()["answer"]

    assert client.post(f"/api/runbooks/{runbook_id}/approve").status_code == 403
    client.post("/api/auth/logout")
    login(client, "approver@example.test", "approver-test-password")
    approved = client.post(f"/api/runbooks/{runbook_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["metadata"]["status"] == "approved"

    published = client.post(f"/api/runbooks/{runbook_id}/publish")
    assert published.status_code == 200
    assert published.json()["metadata"]["status"] == "published"


def test_analysis_requires_authentication(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/repositories/analyze",
        json={"repository_url": "https://github.com/example/project"},
    )

    assert response.status_code == 401


def test_qa_topics_are_focused_and_safe(tmp_path):
    client = make_client(tmp_path)
    login(client, "editor@example.test", "editor-test-password")
    submitted = client.post(
        "/api/repositories/analyze",
        json={"repository_url": "https://github.com/example/project"},
    )
    job = client.get(f"/api/jobs/{submitted.json()['id']}").json()
    assert job["status"] == "completed"
    runbook_id = job["runbook_id"]

    def ask(question):
        return client.post(
            f"/api/runbooks/{runbook_id}/ask",
            json={"question": question},
        ).json()["answer"]

    entry_answer = ask("What entry points are documented?")
    assert "Route handler" in entry_answer
    assert "Failure modes" not in entry_answer

    orders_answer = ask("Where are the orders handled?")
    assert "orders" in orders_answer
    assert "def orders" not in orders_answer
    assert "health" not in orders_answer

    framework_answer = ask("What framework does the service use?")
    assert "Framework: fastapi" in framework_answer
    assert "Review database" not in framework_answer

    file_count_answer = ask("How many files were analyzed?")
    assert "Files analyzed" in file_count_answer
    assert "Repository code was not executed" not in file_count_answer

    commit_answer = ask("What commit was analyzed?")
    assert "Commit:" in commit_answer
    assert "Files analyzed" not in commit_answer

    status_answer = ask("Is this runbook approved?")
    assert status_answer == "The current runbook status is draft."

    dependency_answer = ask("What dependencies are used?")
    assert "fastapi" in dependency_answer
    assert "Failure modes" not in dependency_answer

    serving_dependency_answer = ask("Which dependency is used to serve the application?")
    assert "uvicorn" in serving_dependency_answer
    assert "python:3.12-slim" not in serving_dependency_answer
    assert "Static analysis cannot prove" not in serving_dependency_answer

    timeout_answer = ask("What happens if the API times out?")
    assert "timeout" in timeout_answer.lower()
    assert "Name: Fixture Orders API" not in timeout_answer

    failure_answer = ask("What failure modes were detected?")
    assert "Exception-handling path detected" in failure_answer
    assert "Diagnostic guidance" not in failure_answer

    database_answer = ask("What happens when the database configuration is missing?")
    assert "DATABASE_URL" in database_answer
    assert "REQUEST_TIMEOUT" not in database_answer

    secret_answer = ask("What is the production database password?")
    assert secret_answer == "I cannot provide credentials, secrets, or other sensitive values."

    action_answer = ask("Does the runbook recommend restarting the service?")
    assert action_answer == "The application does not execute commands or perform automatic remediation."

    deploy_answer = ask("Can you deploy this service for me?")
    assert deploy_answer == "The application does not execute commands or perform automatic remediation."

    unknown_answer = ask("What is the capital of France?")
    assert "does not contain enough evidence" in unknown_answer
