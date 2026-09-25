"""Validate analysis evidence against the sanitized manifest."""

from __future__ import annotations

from collections.abc import Iterable

from app.models.analysis import AnalysisResult, Evidence
from app.services.safe_manifest import SafeFileManifest


class EvidenceValidationError(ValueError):
    """Raised when analysis output contains invalid source evidence."""


def validate_evidence(manifest: SafeFileManifest, evidence: Evidence) -> None:
    """Ensure a source reference exists in the sanitized manifest."""
    manifest_paths = {item.path: item for item in manifest.files}
    item = manifest_paths.get(evidence.file)
    if item is None:
        raise EvidenceValidationError(f"Evidence file is not in the safe manifest: {evidence.file}")
    line_count = len(item.sanitized_content.splitlines())
    if evidence.line < 1 or evidence.line > max(line_count, 1):
        raise EvidenceValidationError(f"Evidence line is out of bounds: {evidence.file}:{evidence.line}")
    if evidence.excerpt:
        actual = item.sanitized_content.splitlines()[evidence.line - 1].strip()
        if evidence.excerpt not in actual and actual not in evidence.excerpt:
            raise EvidenceValidationError(
                f"Evidence excerpt does not match the sanitized source: {evidence.file}:{evidence.line}"
            )


def _validate_findings(manifest: SafeFileManifest, findings: Iterable[object]) -> None:
    for finding in findings:
        for evidence in getattr(finding, "evidence", []):
            validate_evidence(manifest, evidence)


def validate_analysis_result(manifest: SafeFileManifest, result: AnalysisResult) -> AnalysisResult:
    """Validate every evidence reference in a combined analysis result."""
    _validate_findings(manifest, result.service.findings)
    _validate_findings(manifest, result.service.entrypoints)
    _validate_findings(manifest, result.service.external_calls)
    _validate_findings(manifest, result.failures.findings)
    _validate_findings(manifest, result.failures.failure_modes)
    _validate_findings(manifest, result.dependencies.findings)
    for dependency in result.dependencies.dependencies:
        validate_evidence(manifest, dependency.evidence)
    _validate_findings(manifest, result.configuration.findings)
    for setting in result.configuration.settings:
        validate_evidence(manifest, setting.evidence)
    return result
