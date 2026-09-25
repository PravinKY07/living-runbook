"""Repository file allowlist and resource-limit policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

ALLOWED_SUFFIXES = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".kts",
    ".md",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
ALLOWED_FILENAMES = {
    ".env.example",
    "build.gradle",
    "Cargo.toml",
    "Dockerfile",
    "Gemfile",
    "Gemfile.lock",
    "go.mod",
    "gradlew",
    "Makefile",
    "package.json",
    "package-lock.json",
    "Pipfile",
    "Pipfile.lock",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "requirements.txt",
    "yarn.lock",
}
BLOCKED_PATH_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
BLOCKED_FILENAMES = {
    ".env",
    "credentials",
    "id_rsa",
    "secrets.yaml",
    "secrets.yml",
}
MAX_ALLOWED_FILE_BYTES = 512_000


class FilePolicyError(ValueError):
    """Raised when a repository path or size is not allowed."""


@dataclass(frozen=True, slots=True)
class FileLimits:
    """Resource limits applied to the safe repository manifest."""

    max_files: int = 500
    max_file_bytes: int = MAX_ALLOWED_FILE_BYTES
    max_total_bytes: int = 10_000_000
    max_path_length: int = 240


def _normalized_relative_path(path: str) -> PurePosixPath:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        raise FilePolicyError("Repository path is invalid.")
    if len(path) > 240 or path.startswith("/"):
        raise FilePolicyError("Repository path is outside the safe limits.")
    relative = PurePosixPath(path)
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise FilePolicyError("Repository path traversal is not allowed.")
    return relative


def is_allowed_file(path: str) -> bool:
    """Return whether a repository file is useful and safe to analyze."""
    try:
        relative = _normalized_relative_path(path)
    except FilePolicyError:
        return False

    if any(part in BLOCKED_PATH_PARTS for part in relative.parts):
        return False
    if relative.name in BLOCKED_FILENAMES:
        return False
    if relative.name.startswith(".env") and relative.name != ".env.example":
        return False
    if relative.suffix.lower() in {".pyc", ".pyo", ".key", ".pem", ".db", ".sqlite", ".zip", ".gz", ".7z"}:
        return False
    return relative.name in ALLOWED_FILENAMES or relative.suffix.lower() in ALLOWED_SUFFIXES


def validate_file_entry(path: str, size_bytes: int, limits: FileLimits | None = None) -> str:
    """Validate one manifest entry and return its normalized relative path."""
    active_limits = limits or FileLimits()
    relative = _normalized_relative_path(path)
    if not is_allowed_file(str(relative)):
        raise FilePolicyError(f"File is not allowed: {relative}")
    if size_bytes < 0 or size_bytes > active_limits.max_file_bytes:
        raise FilePolicyError(f"File exceeds the size limit: {relative}")
    if len(str(relative)) > active_limits.max_path_length:
        raise FilePolicyError(f"File path is too long: {relative}")
    return str(relative)
