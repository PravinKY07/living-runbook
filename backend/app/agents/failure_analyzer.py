"""Static Failure Analyzer."""

from __future__ import annotations

import ast
import re

from app.agents.common import finding, is_test_path, parse_python, python_files
from app.models.analysis import FailureAnalysis, Finding
from app.services.safe_manifest import SafeFileManifest

_TIMEOUT_PATTERN = re.compile(r"\b(timeout|retry|backoff)\b", re.IGNORECASE)
_ERROR_STATUS_PATTERN = re.compile(r"\b(status_code\s*=\s*5\d\d|HTTP\s*5\d\d)\b", re.IGNORECASE)
# Matching the bare word "commit" reported ordinary prose and git messages as
# database operations. Require a database-shaped receiver, an unambiguous data
# call, or a SQL keyword instead.
_DATABASE_PATTERN = re.compile(
    r"\.\s*(?:execute|executemany|executescript|fetchone|fetchall|fetchmany)\s*\("
    r"|\b(?:db|database|conn|connection|cursor|session|engine|pool|sqlite3?)\s*\.\s*"
    r"(?:connect|commit|rollback|close)\s*\("
    r"|\b(?:SELECT\s+[\w*,\s.]+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET"
    r"|DELETE\s+FROM|CREATE\s+TABLE)\b",
    re.IGNORECASE,
)


def analyze_failures(manifest: SafeFileManifest) -> FailureAnalysis:
    """Find error handling and failure signals without executing code."""
    failure_modes: list[Finding] = []
    findings: list[Finding] = []

    for item in python_files(manifest):
        if is_test_path(item.path):
            continue
        tree = parse_python(item)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                mode = finding(
                    kind="try_except",
                    summary="Exception-handling path detected.",
                    item=item,
                    line=node.lineno,
                    confidence="high",
                )
                failure_modes.append(mode)
                findings.append(mode)
            elif isinstance(node, ast.Raise):
                mode = finding(
                    kind="raise",
                    summary="Explicit exception-raising path detected.",
                    item=item,
                    line=node.lineno,
                    confidence="high",
                )
                failure_modes.append(mode)
                findings.append(mode)
            elif isinstance(node, ast.ExceptHandler):
                mode = finding(
                    kind="exception_handler",
                    summary="Exception handler detected.",
                    item=item,
                    line=node.lineno,
                    confidence="high",
                )
                failure_modes.append(mode)
                findings.append(mode)

        for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
            patterns = []
            if _TIMEOUT_PATTERN.search(line):
                patterns.append("timeout_or_retry")
            if _ERROR_STATUS_PATTERN.search(line):
                patterns.append("server_error_response")
            if _DATABASE_PATTERN.search(line):
                patterns.append("database_operation")
            for pattern in patterns:
                mode = finding(
                    kind=pattern,
                    summary=f"Failure signal detected: {pattern.replace('_', ' ')}.",
                    item=item,
                    line=line_number,
                    confidence="medium",
                )
                failure_modes.append(mode)
                findings.append(mode)

    unique = _deduplicate(failure_modes)
    return FailureAnalysis(failure_modes=unique, findings=_deduplicate(findings))


def _deduplicate(values: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str, int]] = set()
    unique: list[Finding] = []
    for value in values:
        evidence = value.evidence[0]
        key = (value.kind, evidence.file, evidence.line)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique
