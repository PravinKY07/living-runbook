"""Accuracy regressions for the static analyzers.

Every test here corresponds to a defect that shipped once: a fabricated
citation, a crash on a well-formed manifest, or a setting mislabelled as an
environment variable. They are written so they cannot pass vacuously.
"""

import pytest

from app.agents.configuration_analyzer import analyze_configuration
from app.agents.dependency_mapper import analyze_dependencies
from app.agents.failure_analyzer import analyze_failures
from app.security.redaction import REDACTED_TOKEN, redact_text
from app.services.runbook_store import (
    RunbookApprovalError,
    RunbookIntegrityError,
    SQLiteRunbookStore,
)
from app.services.runbook_writer import RunbookWriter
from app.services.safe_manifest import ManifestFile, SafeFileManifest


def manifest_for(path: str, content: str) -> SafeFileManifest:
    return SafeFileManifest(
        files=(ManifestFile(path=path, size_bytes=len(content), sanitized_content=content),),
        skipped=(),
        total_bytes=len(content),
        repository_commit="abc1234",
    )


def cited_lines(dependencies) -> dict[str, int]:
    return {item.name: item.evidence.line for item in dependencies}


# --- pyproject.toml: PEP 621 dependencies carry no line numbers -------------


PYPROJECT = """[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn>=0.20.0",
]
"""


def test_pyproject_dependencies_cite_their_real_line():
    """A JSON/TOML array index is not a source line. The cited line must hold
    the dependency text itself."""
    result = analyze_dependencies(manifest_for("pyproject.toml", PYPROJECT))
    lines = PYPROJECT.splitlines()

    assert cited_lines(result.dependencies) == {"fastapi": 5, "uvicorn": 6}
    for dependency in result.dependencies:
        excerpt = lines[dependency.evidence.line - 1]
        assert dependency.name in excerpt, f"{dependency.name} cited a line that omits it"


def test_pyproject_optional_dependencies_cite_their_real_line():
    content = (
        "[project]\n"
        'name = "demo"\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=7.0"]\n'
    )
    result = analyze_dependencies(manifest_for("pyproject.toml", content))

    assert cited_lines(result.dependencies) == {"pytest": 4}
    assert result.dependencies[0].category == "development"


# --- package.json: same defect, same fix -----------------------------------

PACKAGE_JSON = """{
  "name": "demo",
  "dependencies": {
    "react": "^18.0.0",
    "axios": "^1.0.0"
  }
}
"""


def test_package_json_dependencies_cite_their_real_line():
    result = analyze_dependencies(manifest_for("package.json", PACKAGE_JSON))
    lines = PACKAGE_JSON.splitlines()

    assert cited_lines(result.dependencies) == {"react": 4, "axios": 5}
    for dependency in result.dependencies:
        assert f'"{dependency.name}"' in lines[dependency.evidence.line - 1]


@pytest.mark.parametrize(
    "content",
    [
        '{"name": "x", "dependencies": []}',
        '{"name": "x", "dependencies": "react"}',
        '{"name": "x", "dependencies": null}',
        '{"name": "x", "devDependencies": []}',
        "[]",
    ],
)
def test_malformed_package_json_is_ignored_not_fatal(content):
    """"dependencies": [] is valid JSON. It must not raise AttributeError and
    strand the analysis job in a running state forever."""
    assert analyze_dependencies(manifest_for("package.json", content)).dependencies == []


@pytest.mark.parametrize(
    "content",
    [
        '[project]\nname = "x"\ndependencies = "fastapi>=1"\n',
        '[project]\nname = "x"\noptional-dependencies = "oops"\n',
        '[project]\nname = "x"\ndependencies = [1, 2, 3]\n',
    ],
)
def test_malformed_pyproject_is_ignored_not_fatal(content):
    """A string where a list belongs must not be iterated character by character
    into dozens of one-letter 'dependencies'."""
    assert analyze_dependencies(manifest_for("pyproject.toml", content)).dependencies == []


# --- Dockerfile: build flags and multi-stage references --------------------


def test_dockerfile_ignores_platform_flags_and_build_stages():
    content = (
        "FROM --platform=linux/amd64 python:3.11-slim AS builder\n"
        "RUN pip install example\n"
        "FROM builder\n"
        "FROM alpine:3.19\n"
    )
    result = analyze_dependencies(manifest_for("Dockerfile", content))

    # The image, not the --platform flag. The second FROM copies stage "builder"
    # and is not a registry image.
    assert [item.name for item in result.dependencies] == ["python:3.11-slim", "alpine:3.19"]
    assert cited_lines(result.dependencies) == {"python:3.11-slim": 1, "alpine:3.19": 4}


# --- configuration: a constant is not an environment variable --------------


def test_module_constant_is_not_reported_as_an_environment_variable():
    content = 'import os\nMAX_ATTEMPTS = 2\nDATABASE_URL = os.getenv("DATABASE_URL")\n'
    result = analyze_configuration(manifest_for("app.py", content))
    kinds = {item.name: item.kind for item in result.settings}

    assert kinds["MAX_ATTEMPTS"] == "constant"
    assert kinds["DATABASE_URL"] == "environment"


def test_environment_variable_with_inline_default_stays_environment():
    content = 'import os\nDB = os.getenv("DATABASE_URL", "sqlite:///app.db")\n'
    result = analyze_configuration(manifest_for("app.py", content))

    assert {(item.name, item.kind) for item in result.settings} >= {("DATABASE_URL", "environment")}


def test_runbook_renders_a_constant_without_claiming_it_is_environment(tmp_path):
    (tmp_path / "app.py").write_text("MAX_ATTEMPTS = 2\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi>=0.100.0\n", encoding="utf-8")
    from app.services.analysis_service import analyze_manifest
    from app.services.safe_manifest import build_safe_manifest

    manifest = build_safe_manifest(tmp_path, repository_commit="abc1234")
    draft = RunbookWriter().write(analyze_manifest(manifest))

    assert "`MAX_ATTEMPTS` (constant)" in draft.content
    assert "`MAX_ATTEMPTS` (environment)" not in draft.content


# --- failure analyzer: prose is not a database operation -------------------


def test_bare_commit_in_prose_is_not_a_database_operation():
    content = "# we commit to shipping weekly\ndef commit():\n    return None\n"
    result = analyze_failures(manifest_for("app.py", content))

    assert "database_operation" not in {item.kind for item in result.failure_modes}


def test_real_database_operations_are_still_detected(tmp_path):
    (tmp_path / "db.py").write_text(
        "def run(conn):\n    conn.execute('SELECT 1')\n    rows = conn.fetchall()\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi>=0.100.0\n", encoding="utf-8")
    from app.services.analysis_service import analyze_manifest
    from app.services.safe_manifest import build_safe_manifest

    manifest = build_safe_manifest(tmp_path, repository_commit="abc1234")
    result = analyze_manifest(manifest)

    assert "database_operation" in {item.kind for item in result.failures.failure_modes}


# --- redaction: a JWT is a bearer credential -------------------------------

JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27u"


def test_json_web_token_is_redacted_even_without_a_secret_shaped_name():
    redacted = redact_text(f'SESSION = "{JWT}"')

    assert JWT not in redacted
    assert REDACTED_TOKEN in redacted


def test_ordinary_dotted_text_is_not_mistaken_for_a_token():
    text = "version = 1.2.3\nmodule.name = value\n"

    assert redact_text(text) == text


# --- storage integrity is not an authorization problem ---------------------


def test_tampered_content_raises_an_integrity_error_not_an_approval_error(tmp_path):
    """A hash mismatch is a storage failure. Reporting it as RunbookApprovalError
    made a corrupted store answer 403 Forbidden, an authorization lie."""
    import hashlib
    from datetime import UTC, datetime

    from app.models.runbook import RunbookDraft, RunbookMetadata

    content = "# Service Runbook\n\n- Provider: `static`\n"
    draft = RunbookDraft(
        content=content,
        metadata=RunbookMetadata(
            version=1,
            repository_url="https://github.com/example/project",
            repository_commit="abc1234",
            provider="static",
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            created_at=datetime.now(UTC),
        ),
    )
    store = SQLiteRunbookStore(str(tmp_path / "runbooks.db"))
    stored = store.create_draft(draft)
    store._connect().execute(
        "UPDATE runbook_versions SET content = ? WHERE runbook_id = ?",
        ("# Service Runbook\n\n- Provider: `mock`\n", stored.runbook_id),
    )
    store._connect().commit()

    with pytest.raises(RunbookIntegrityError):
        store.get(stored.runbook_id)

    # It must not be catchable as an approval/permission decision.
    assert not issubclass(RunbookIntegrityError, RunbookApprovalError)


# --- the Evidence section must index every citation the runbook makes ------


def test_evidence_section_includes_dependency_and_configuration_citations(tmp_path):
    (tmp_path / "app.py").write_text("MAX_ATTEMPTS = 2\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi>=0.100.0\n", encoding="utf-8")
    from app.services.analysis_service import analyze_manifest
    from app.services.safe_manifest import build_safe_manifest

    manifest = build_safe_manifest(tmp_path, repository_commit="abc1234")
    analysis = analyze_manifest(manifest)
    draft = RunbookWriter().write(analysis)
    evidence_section = draft.content.split("## Evidence", 1)[1].split("## Limitations", 1)[0]

    for item in analysis.dependencies.dependencies:
        assert f"`{item.evidence.file}:{item.evidence.line}`" in evidence_section
    for setting in analysis.configuration.settings:
        assert f"`{setting.evidence.file}:{setting.evidence.line}`" in evidence_section


def test_evidence_section_has_no_duplicate_lines(tmp_path):
    (tmp_path / "app.py").write_text("import os\nX = 1\nY = 2\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi>=0.100.0\nrequests==2.31.0\n", encoding="utf-8")
    from app.services.analysis_service import analyze_manifest
    from app.services.safe_manifest import build_safe_manifest

    manifest = build_safe_manifest(tmp_path, repository_commit="abc1234")
    draft = RunbookWriter().write(analyze_manifest(manifest))
    evidence_section = draft.content.split("## Evidence", 1)[1].split("## Limitations", 1)[0]
    cited = [line for line in evidence_section.splitlines() if line.startswith("- `")]

    assert cited, "the fixture must produce evidence, or this test proves nothing"
    assert len(cited) == len(set(cited))
