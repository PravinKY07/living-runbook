"""Run the four bounded static analyzers over a sanitized manifest."""

from __future__ import annotations

from app.agents.configuration_analyzer import analyze_configuration
from app.agents.dependency_mapper import analyze_dependencies
from app.agents.failure_analyzer import analyze_failures
from app.agents.service_mapper import analyze_services
from app.models.analysis import AnalysisResult
from app.security.evidence import validate_analysis_result
from app.services.safe_manifest import SafeFileManifest


def analyze_manifest(
    manifest: SafeFileManifest,
    *,
    repository_url: str | None = None,
) -> AnalysisResult:
    """Produce a validated static analysis result."""
    result = AnalysisResult(
        provider="static",
        repository_url=repository_url,
        repository_commit=manifest.repository_commit,
        files_analyzed=len(manifest.files),
        service=analyze_services(manifest),
        failures=analyze_failures(manifest),
        dependencies=analyze_dependencies(manifest),
        configuration=analyze_configuration(manifest),
    )
    return validate_analysis_result(manifest, result)
