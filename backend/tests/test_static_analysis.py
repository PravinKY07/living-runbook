import pytest

from app.models.analysis import Evidence
from app.security.evidence import (
    EvidenceValidationError,
    validate_analysis_result,
    validate_evidence,
)
from app.services.analysis_service import analyze_manifest
from app.services.safe_manifest import SafeFileManifest, build_safe_manifest


def make_fixture_manifest(tmp_path) -> SafeFileManifest:
    (tmp_path / "app.py").write_text(
        """
from fastapi import FastAPI
import os
import requests

app = FastAPI(title="Demo API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/orders")
def orders():
    try:
        timeout = 5
        connection = db.connect()
        return requests.get("https://service.example/orders", timeout=timeout)
    except Exception:
        raise RuntimeError("order service failed")

def database_url():
    return os.getenv("DATABASE_URL")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "fastapi>=0.100.0\nrequests==2.31.0\n",
        encoding="utf-8",
    )
    (tmp_path / "config.py").write_text(
        'DEBUG = False\nLOG_LEVEL = "INFO"\n',
        encoding="utf-8",
    )
    return build_safe_manifest(tmp_path, repository_commit="abc1234")


def make_docstring_manifest(tmp_path) -> SafeFileManifest:
    (tmp_path / "app.py").write_text(
        '"""A small FastAPI orders service used to demonstrate analysis.\n'
        "\n"
        "It exposes a health check and an orders endpoint, and enriches orders\n"
        'with stock levels from an external inventory service over HTTP.\n'
        '"""\n'
        "\n"
        "from fastapi import FastAPI\n"
        "\n"
        'app = FastAPI(title="Fixture Orders API")\n'
        "\n"
        '@app.get("/health")\n'
        "def health():\n"
        '    return {"status": "ok"}\n',
        encoding="utf-8",
    )
    return build_safe_manifest(tmp_path, repository_commit="abc1234")


def test_service_mapper_derives_purpose_from_module_docstring(tmp_path):
    result = analyze_manifest(make_docstring_manifest(tmp_path))

    # Only the leading summary sentence is used, never the trailing prose.
    assert result.service.purpose == "A small FastAPI orders service used to demonstrate analysis."
    assert result.service.purpose_evidence is not None
    assert result.service.purpose_evidence.file == "app.py"
    assert result.service.purpose_evidence.line == 1


def test_service_mapper_leaves_purpose_unknown_without_a_docstring(tmp_path):
    result = analyze_manifest(make_fixture_manifest(tmp_path))

    assert result.service.purpose is None
    assert result.service.purpose_evidence is None


def test_purpose_evidence_is_validated_like_every_other_claim(tmp_path):
    manifest = make_docstring_manifest(tmp_path)
    result = analyze_manifest(manifest)

    # A real docstring citation passes validation.
    assert result.service.purpose_evidence is not None
    validate_evidence(manifest, result.service.purpose_evidence)

    # A purpose pointing outside the manifest must be rejected, not waved past.
    tampered = result.model_copy(
        update={
            "service": result.service.model_copy(
                update={"purpose_evidence": Evidence(file="missing.py", line=1, excerpt=None)}
            )
        }
    )
    with pytest.raises(EvidenceValidationError):
        validate_analysis_result(manifest, tampered)


def test_service_mapper_finds_routes_framework_and_external_calls(tmp_path):
    result = analyze_manifest(make_fixture_manifest(tmp_path))

    assert result.provider == "static"
    assert result.service.framework == "fastapi"
    assert {item.kind for item in result.service.entrypoints} == {"route"}
    assert any("requests.get" in item.summary for item in result.service.external_calls)


def test_failure_mapper_finds_error_and_timeout_paths(tmp_path):
    result = analyze_manifest(make_fixture_manifest(tmp_path))

    kinds = {item.kind for item in result.failures.failure_modes}
    assert "try_except" in kinds
    assert "exception_handler" in kinds
    assert "raise" in kinds
    assert "timeout_or_retry" in kinds
    assert "database_operation" in kinds


def test_dependency_mapper_reads_requirements(tmp_path):
    result = analyze_manifest(make_fixture_manifest(tmp_path))

    names = {item.name for item in result.dependencies.dependencies}
    assert {"fastapi", "requests"}.issubset(names)


def test_configuration_mapper_reports_names_without_values(tmp_path):
    result = analyze_manifest(make_fixture_manifest(tmp_path))

    names = {item.name for item in result.configuration.settings}
    assert "DATABASE_URL" in names
    assert "DEBUG" in names
    assert "LOG_LEVEL" in names
    assert all(item.value_summary is None for item in result.configuration.settings)


def test_analysis_result_contains_valid_evidence(tmp_path):
    manifest = make_fixture_manifest(tmp_path)

    result = analyze_manifest(manifest, repository_url="https://github.com/example/project")

    assert result.repository_url == "https://github.com/example/project"
    assert result.repository_commit == "abc1234"
    assert result.files_analyzed == len(manifest.files)
    assert result.service.entrypoints[0].evidence[0].file == "app.py"
    assert result.service.entrypoints[0].evidence[0].line > 0


def test_invalid_evidence_is_rejected(tmp_path):
    manifest = make_fixture_manifest(tmp_path)

    with pytest.raises(EvidenceValidationError):
        validate_evidence(
            manifest,
            Evidence(file="missing.py", line=1, excerpt=None),
        )

    with pytest.raises(EvidenceValidationError):
        validate_evidence(
            manifest,
            Evidence(file="app.py", line=9999, excerpt=None),
        )
