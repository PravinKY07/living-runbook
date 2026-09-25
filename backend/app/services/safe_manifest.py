"""Build a bounded, redacted manifest from a temporary repository workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.security.file_policy import (
    FileLimits,
    FilePolicyError,
    is_allowed_file,
    validate_file_entry,
)
from app.security.redaction import redact_text


class RepositoryLimitError(RuntimeError):
    """Raised when a repository exceeds a manifest resource limit."""


@dataclass(frozen=True, slots=True)
class ManifestFile:
    """One safe, redacted source file held only for the analysis window."""

    path: str
    size_bytes: int
    sanitized_content: str


@dataclass(frozen=True, slots=True)
class ManifestSkip:
    """A path deliberately excluded from analysis."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class SafeFileManifest:
    """Sanitized repository content plus non-sensitive skip metadata."""

    files: tuple[ManifestFile, ...]
    skipped: tuple[ManifestSkip, ...]
    total_bytes: int
    repository_commit: str | None = None


def manifest_to_dict(manifest: SafeFileManifest) -> dict:
    """Serialize a sanitized manifest for an internal provider request."""
    return {
        "files": [
            {
                "path": item.path,
                "size_bytes": item.size_bytes,
                "sanitized_content": item.sanitized_content,
            }
            for item in manifest.files
        ],
        "skipped": [
            {"path": item.path, "reason": item.reason}
            for item in manifest.skipped
        ],
        "total_bytes": manifest.total_bytes,
        "repository_commit": manifest.repository_commit,
    }


def manifest_from_dict(data: dict) -> SafeFileManifest:
    """Rebuild a manifest from internal, already-sanitized provider data."""
    if not isinstance(data, dict):
        raise TypeError("Manifest data must be an object.")
    files = tuple(
        ManifestFile(
            path=str(item["path"]),
            size_bytes=int(item["size_bytes"]),
            sanitized_content=redact_text(str(item["sanitized_content"])),
        )
        for item in data.get("files", [])
    )
    skipped = tuple(
        ManifestSkip(path=str(item["path"]), reason=str(item["reason"]))
        for item in data.get("skipped", [])
    )
    return SafeFileManifest(
        files=files,
        skipped=skipped,
        total_bytes=int(data.get("total_bytes", 0)),
        repository_commit=data.get("repository_commit"),
    )


def build_safe_manifest(
    root: Path,
    *,
    repository_commit: str | None = None,
    limits: FileLimits | None = None,
) -> SafeFileManifest:
    """Collect allowlisted text files without following symlinks."""
    active_limits = limits or FileLimits()
    root = root.resolve()
    files: list[ManifestFile] = []
    skipped: list[ManifestSkip] = []
    total_bytes = 0

    for directory, directory_names, file_names in _walk_without_symlinks(root):
        for file_name in file_names:
            path = Path(directory) / file_name
            relative_path = path.relative_to(root).as_posix()

            if path.is_symlink():
                skipped.append(ManifestSkip(relative_path, "symlink"))
                continue

            try:
                path.resolve().relative_to(root)
            except ValueError as exc:
                raise RepositoryLimitError("A repository path escaped the workspace root.") from exc

            if not is_allowed_file(relative_path):
                skipped.append(ManifestSkip(relative_path, "not_allowlisted"))
                continue

            size_bytes = path.stat().st_size
            if size_bytes > active_limits.max_file_bytes:
                skipped.append(ManifestSkip(relative_path, "file_too_large"))
                continue

            if len(files) >= active_limits.max_files:
                raise RepositoryLimitError("Repository exceeds the allowed file count.")

            try:
                safe_path = validate_file_entry(relative_path, size_bytes, active_limits)
            except FilePolicyError as exc:
                raise RepositoryLimitError(str(exc)) from exc

            total_bytes += size_bytes
            if total_bytes > active_limits.max_total_bytes:
                raise RepositoryLimitError("Repository exceeds the allowed total size.")

            content = path.read_text(encoding="utf-8", errors="replace")
            files.append(
                ManifestFile(
                    path=safe_path,
                    size_bytes=size_bytes,
                    sanitized_content=redact_text(content),
                )
            )

    files.sort(key=lambda item: item.path)
    skipped.sort(key=lambda item: item.path)
    return SafeFileManifest(
        files=tuple(files),
        skipped=tuple(skipped),
        total_bytes=total_bytes,
        repository_commit=repository_commit,
    )


def _walk_without_symlinks(root: Path):
    """Yield directories while pruning symlinked directories."""
    pending = [root]
    while pending:
        directory = pending.pop()
        for child in directory.iterdir():
            if child.is_symlink():
                continue
            if child.is_dir():
                pending.append(child)
                yield directory, [child.name], []
            elif child.is_file():
                yield directory, [], [child.name]
