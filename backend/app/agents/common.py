"""Static analysis helpers shared by the four bounded analyzers."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import PurePosixPath

from app.models.analysis import Evidence, Finding
from app.services.safe_manifest import ManifestFile, SafeFileManifest


def python_files(manifest: SafeFileManifest) -> Iterator[ManifestFile]:
    """Yield allowlisted Python files from the manifest."""
    for item in manifest.files:
        if item.path.endswith(".py"):
            yield item


def manifest_file(manifest: SafeFileManifest, path: str) -> ManifestFile | None:
    """Find a manifest file by its normalized path."""
    return next((item for item in manifest.files if item.path == path), None)


def line_excerpt(content: str, line: int, limit: int = 200) -> str | None:
    """Return a short, already-redacted source excerpt."""
    lines = content.splitlines()
    if line < 1 or line > len(lines):
        return None
    excerpt = lines[line - 1].strip()
    return excerpt[:limit] if excerpt else None


def evidence_for(item: ManifestFile, line: int) -> Evidence:
    """Create evidence for a manifest file and line."""
    return Evidence(
        file=item.path,
        line=line,
        excerpt=line_excerpt(item.sanitized_content, line),
    )


def finding(
    *,
    kind: str,
    summary: str,
    item: ManifestFile,
    line: int,
    confidence: str = "medium",
    recommendation: str | None = None,
) -> Finding:
    """Create a finding with one source reference."""
    return Finding(
        kind=kind,
        summary=summary,
        evidence=[evidence_for(item, line)],
        confidence=confidence,
        recommendation=recommendation,
    )


def parse_python(item: ManifestFile) -> ast.Module | None:
    """Parse a sanitized Python file without executing it."""
    try:
        return ast.parse(item.sanitized_content, filename=item.path)
    except SyntaxError:
        return None


def relative_name(path: str) -> str:
    """Return a readable final path component."""
    return PurePosixPath(path).name


def is_test_path(path: str) -> bool:
    """Return whether a path looks like a test file or directory."""
    parts = PurePosixPath(path).parts
    return any(part == "tests" or part.startswith("test_") for part in parts)
