"""Read-only, temporary GitHub repository loading."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.security.file_policy import FileLimits
from app.security.url_policy import (
    GitHubRepository,
    validate_github_repository_url,
    validate_public_hostname,
)
from app.services.safe_manifest import SafeFileManifest, build_safe_manifest

GitRunner = Callable[..., subprocess.CompletedProcess[str]]
HostnameResolver = Callable[[str], list[str]]


class RepositoryLoadError(RuntimeError):
    """Raised when the validated repository cannot be loaded safely."""


class RepositoryCleanupError(RuntimeError):
    """Raised when a temporary workspace cannot be removed."""


@dataclass(frozen=True, slots=True)
class LoadedRepository:
    """A temporary repository and its sanitized manifest."""

    repository: GitHubRepository
    root: Path
    manifest: SafeFileManifest


def _safe_git_environment() -> dict[str, str]:
    """Return a minimal environment that cannot prompt for credentials."""
    safe_names = {
        "HOMEDRIVE",
        "HOMEPATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {
        name: os.environ[name]
        for name in safe_names
        if name in os.environ
    }
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    return environment


class RepositoryLoader:
    """Clone a public repository into a disposable workspace."""

    def __init__(
        self,
        *,
        git_executable: str = "git",
        clone_timeout_seconds: int = 120,
        limits: FileLimits | None = None,
        runner: GitRunner | None = None,
        resolver: HostnameResolver | None = None,
    ) -> None:
        self._git_executable = git_executable
        self._clone_timeout_seconds = clone_timeout_seconds
        self._limits = limits or FileLimits()
        self._runner = runner or subprocess.run
        self._resolver = resolver

    @contextmanager
    def load(self, url: str) -> Iterator[LoadedRepository]:
        """Yield a loaded repository and always remove the temporary workspace."""
        repository = validate_github_repository_url(url)
        workspace = Path(tempfile.mkdtemp(prefix="living-runbook-"))
        destination = workspace / "repository"

        try:
            self._clone(repository, workspace, destination)
            commit = self._read_commit(destination)
            manifest = build_safe_manifest(
                destination,
                repository_commit=commit,
                limits=self._limits,
            )
            yield LoadedRepository(
                repository=repository,
                root=destination,
                manifest=manifest,
            )
        except Exception:
            self._cleanup(workspace)
            raise
        else:
            self._cleanup(workspace)

    def _clone(
        self,
        repository: GitHubRepository,
        workspace: Path,
        destination: Path,
    ) -> None:
        if self._resolver is None:
            validate_public_hostname("github.com")
        else:
            validate_public_hostname("github.com", resolver=self._resolver)
        command = [
            self._git_executable,
            "-c",
            "core.symlinks=false",
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "protocol.file.allow=never",
            "-c",
            "protocol.ssh.allow=never",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--no-tags",
            "--no-recurse-submodules",
            repository.normalized_url,
            str(destination),
        ]
        try:
            result = self._runner(
                command,
                cwd=workspace,
                env=_safe_git_environment(),
                capture_output=True,
                text=True,
                timeout=self._clone_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryLoadError("Repository clone failed safely.") from exc

        if result.returncode != 0 or not destination.is_dir():
            raise RepositoryLoadError("Repository clone failed safely.")

    def _read_commit(self, root: Path) -> str | None:
        try:
            result = self._runner(
                [
                    self._git_executable,
                    "-C",
                    str(root),
                    "rev-parse",
                    "HEAD",
                ],
                cwd=root,
                env=_safe_git_environment(),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        commit = result.stdout.strip()
        return commit if re.fullmatch(r"[0-9a-fA-F]{7,64}", commit) else None

    @staticmethod
    def _cleanup(workspace: Path) -> None:
        def clear_readonly(function, path, _exc_info) -> None:
            os.chmod(path, stat.S_IWRITE)
            function(path)

        for attempt in range(3):
            try:
                shutil.rmtree(workspace, onerror=clear_readonly)
                return
            except OSError:
                if attempt == 2:
                    raise RepositoryCleanupError(
                        "Temporary repository workspace could not be removed."
                    )
                time.sleep(0.1)
