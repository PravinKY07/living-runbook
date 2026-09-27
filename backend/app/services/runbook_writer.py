"""Deterministic Markdown Runbook Writer."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.models.analysis import AnalysisResult, Finding
from app.models.runbook import RunbookDraft, RunbookMetadata
from app.security.runbook_scan import require_safe_runbook


class RunbookWriter:
    """Turn validated static analysis into a reviewable Markdown draft."""

    prompt_version = "runbook-writer-v1"

    def write(
        self,
        analysis: AnalysisResult,
        *,
        version: int = 1,
        created_at: datetime | None = None,
    ) -> RunbookDraft:
        """Generate, scan, and describe a runbook draft."""
        content = self._render(analysis)
        require_safe_runbook(content)
        timestamp = created_at or datetime.now(UTC)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return RunbookDraft(
            content=content,
            metadata=RunbookMetadata(
                version=version,
                repository_url=analysis.repository_url,
                repository_commit=analysis.repository_commit,
                provider=analysis.provider,
                prompt_version=self.prompt_version,
                content_hash=content_hash,
                status="draft",
                created_at=timestamp,
            ),
        )

    def _render(self, analysis: AnalysisResult) -> str:
        service = analysis.service
        purpose_evidence = (
            f" — evidence: `{service.purpose_evidence.file}:{service.purpose_evidence.line}`"
            if service.purpose_evidence
            else ""
        )
        lines = [
            "# Service Runbook",
            "",
            "> Generated from sanitized static analysis. Human approval is required before publishing.",
            "",
            "## Provenance",
            "",
            f"- Provider: `{analysis.provider}`",
            f"- Repository: `{analysis.repository_url or 'not provided'}`",
            f"- Commit: `{analysis.repository_commit or 'not recorded'}`",
            f"- Files analyzed: `{analysis.files_analyzed}`",
            "- Repository code was not executed.",
            "",
            "## Service overview",
            "",
            f"- Name: {service.service_name or 'Not established by static analysis'}",
            f"- Purpose: {service.purpose or 'Not established by static analysis'}{purpose_evidence}",
            f"- Language: {service.language or 'Not established by static analysis'}",
            f"- Framework: {service.framework or 'Not established by static analysis'}",
            "",
            "## Entry points",
            "",
        ]
        lines.extend(_render_findings(service.entrypoints, "No route entry points were detected."))
        lines.extend(["", "## External calls", ""])
        lines.extend(_render_findings(service.external_calls, "No external call candidates were detected."))

        lines.extend(["", "## Dependencies", ""])
        if analysis.dependencies.dependencies:
            for dependency in analysis.dependencies.dependencies:
                version = f" {dependency.version}" if dependency.version else ""
                evidence = dependency.evidence
                lines.append(
                    f"- `{dependency.name}`{version} — {dependency.category}; "
                    f"evidence: `{evidence.file}:{evidence.line}`"
                )
        else:
            lines.append("No dependencies were detected in the safe manifest.")

        lines.extend(["", "## Configuration", ""])
        if analysis.configuration.settings:
            for setting in analysis.configuration.settings:
                evidence = setting.evidence
                lines.append(
                    f"- `{setting.name}` ({setting.kind}) — "
                    f"evidence: `{evidence.file}:{evidence.line}`; value withheld"
                )
        else:
            lines.append("No configuration references were detected.")

        lines.extend(["", "## Failure modes", ""])
        lines.extend(
            _render_findings(
                analysis.failures.failure_modes,
                "No failure-handling paths were detected.",
            )
        )

        lines.extend(
            [
                "",
                "## Diagnostic guidance",
                "",
                "- Confirm the cited file and line before acting on a finding.",
                "- Check the referenced configuration names without exposing their values.",
                "- Review database and external-service error handling before maintenance.",
                "- Generated commands are not executed by this application.",
                "",
                "## Evidence",
                "",
            ]
        )
        seen_evidence: set[tuple[str, int, str]] = set()
        for finding in _all_findings(analysis):
            for evidence in finding.evidence:
                excerpt = evidence.excerpt or "source excerpt unavailable"
                # One source line can back several findings (two configuration
                # names on one line, for example). Cite it once.
                key = (evidence.file, evidence.line, excerpt)
                if key in seen_evidence:
                    continue
                seen_evidence.add(key)
                lines.append(f"- `{evidence.file}:{evidence.line}` — {excerpt}")
        if not _all_findings(analysis):
            lines.append("- No evidence-backed findings were produced.")

        lines.extend(
            [
                "",
                "## Limitations",
                "",
                "- Static analysis cannot prove runtime behavior or deployment state.",
                "- Unknown facts remain unknown rather than being invented.",
                "- This draft requires an Approver before publication.",
                "",
            ]
        )
        return "\n".join(lines)


def _all_findings(analysis: AnalysisResult) -> list[Finding]:
    return (
        analysis.service.findings
        + analysis.failures.findings
        + analysis.dependencies.findings
        + analysis.configuration.findings
    )


def _render_findings(findings: list[Finding], empty_message: str) -> list[str]:
    if not findings:
        return [f"- {empty_message}"]
    lines: list[str] = []
    for finding in findings:
        evidence = finding.evidence[0] if finding.evidence else None
        location = f" — `{evidence.file}:{evidence.line}`" if evidence else ""
        lines.append(f"- **{finding.kind}**: {finding.summary}{location}")
    return lines
