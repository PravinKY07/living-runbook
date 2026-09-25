from pathlib import Path

import pytest

from app.models.analysis import AnalysisResult
from app.security.runbook_scan import UnsafeRunbookError, require_safe_runbook, scan_runbook
from app.services.analysis_service import analyze_manifest
from app.services.runbook_store import (
    RunbookApprovalError,
    SQLiteRunbookStore,
)
from app.services.runbook_writer import RunbookWriter
from app.services.safe_manifest import build_safe_manifest


def make_analysis(tmp_path: Path) -> AnalysisResult:
    (tmp_path / "app.py").write_text(
        """
from fastapi import FastAPI

app = FastAPI(title="Demo API")

@app.get("/health")
def health():
    return {"status": "ok"}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi>=0.100.0\n", encoding="utf-8")
    manifest = build_safe_manifest(tmp_path, repository_commit="abc1234")
    return analyze_manifest(manifest, repository_url="https://github.com/example/project")


def test_writer_generates_evidence_backed_markdown(tmp_path):
    draft = RunbookWriter().write(make_analysis(tmp_path))

    assert draft.metadata.provider == "static"
    assert draft.metadata.repository_commit == "abc1234"
    assert draft.metadata.status == "draft"
    assert draft.content.startswith("# Service Runbook")
    assert "## Entry points" in draft.content
    assert "## Failure modes" in draft.content
    assert "app.py:" in draft.content
    assert "Human approval is required" in draft.content
    assert "API_KEY" not in draft.content


def test_final_runbook_scan_blocks_secret_content():
    result = scan_runbook("API_KEY=real-looking-value")

    assert result.safe is False
    with pytest.raises(UnsafeRunbookError):
        require_safe_runbook("password=real-looking-value")


def test_runbook_store_enforces_approval_before_publish(tmp_path):
    draft = RunbookWriter().write(make_analysis(tmp_path))
    store = SQLiteRunbookStore(str(tmp_path / "runbooks.db"))
    stored = store.create_draft(draft)

    assert store.get(stored.runbook_id).draft.metadata.status == "draft"
    assert len(store.list_versions(stored.runbook_id)) == 1

    with pytest.raises(RunbookApprovalError):
        store.approve(stored.runbook_id, approver_id=7, role="editor")

    approved = store.approve(stored.runbook_id, approver_id=7, role="approver")
    assert approved.draft.metadata.status == "approved"
    assert approved.draft.metadata.approved_by == 7

    with pytest.raises(RunbookApprovalError):
        store.publish(stored.runbook_id, role="editor")

    published = store.publish(stored.runbook_id, role="approver")
    assert published.draft.metadata.status == "published"
    assert store.get(stored.runbook_id).draft.metadata.status == "published"


def test_runbook_store_preserves_content_hash(tmp_path):
    draft = RunbookWriter().write(make_analysis(tmp_path))
    store = SQLiteRunbookStore(str(tmp_path / "runbooks.db"))
    stored = store.create_draft(draft)

    loaded = store.get(stored.runbook_id)

    assert loaded.draft.metadata.content_hash == draft.metadata.content_hash
    assert len(loaded.draft.metadata.content_hash) == 64
