import subprocess
from pathlib import Path

import pytest

from app.security.file_policy import FileLimits
from app.security.url_policy import URLPolicyError
from app.services.repository_loader import (
    RepositoryLoader,
    RepositoryLoadError,
)
from app.services.safe_manifest import RepositoryLimitError, build_safe_manifest


class FakeGitRunner:
    def __init__(self, *, clone_returncode: int = 0) -> None:
        self.clone_returncode = clone_returncode
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "clone" in command:
            destination = Path(command[-1])
            if self.clone_returncode == 0:
                destination.mkdir(parents=True)
                (destination / "app.py").write_text(
                    "API_KEY=should-be-redacted\nprint('ok')\n",
                    encoding="utf-8",
                )
                (destination / ".env").write_text("PASSWORD=do-not-include\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, self.clone_returncode, "", "")
        if "rev-parse" in command:
            return subprocess.CompletedProcess(command, 0, "a" * 40, "")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_loader_uses_read_only_clone_flags_and_cleans_workspace():
    runner = FakeGitRunner()
    loader = RepositoryLoader(runner=runner, resolver=lambda _: ["8.8.8.8"])
    saved_root: Path | None = None

    with loader.load("https://github.com/example/project") as loaded:
        saved_root = loaded.root
        assert saved_root.exists()
        assert loaded.repository.normalized_url == "https://github.com/example/project"
        assert loaded.manifest.repository_commit == "a" * 40
        assert [item.path for item in loaded.manifest.files] == ["app.py"]
        assert "should-be-redacted" not in loaded.manifest.files[0].sanitized_content
        assert ".env" in {item.path for item in loaded.manifest.skipped}

        clone_command = next(command for command in runner.calls if "clone" in command)
        assert "--depth" in clone_command
        assert "1" in clone_command
        assert "--no-recurse-submodules" in clone_command
        assert "--no-tags" in clone_command
        assert "core.symlinks=false" in clone_command
        assert "protocol.file.allow=never" in clone_command
        assert "protocol.ssh.allow=never" in clone_command

    assert saved_root is not None
    assert not saved_root.exists()


def test_loader_rejects_invalid_url_before_running_git():
    runner = FakeGitRunner()

    with pytest.raises(URLPolicyError), RepositoryLoader(runner=runner, resolver=lambda _: ["8.8.8.8"]).load(
        "https://evil.example/project"
    ):
        pass

    assert runner.calls == []


def test_loader_fails_safely_when_clone_fails():
    runner = FakeGitRunner(clone_returncode=1)

    with pytest.raises(RepositoryLoadError), RepositoryLoader(runner=runner, resolver=lambda _: ["8.8.8.8"]).load(
        "https://github.com/example/project"
    ):
        pass

    assert runner.calls


def test_manifest_enforces_file_count_limit(tmp_path):
    (tmp_path / "one.py").write_text("one = 1\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("two = 2\n", encoding="utf-8")

    with pytest.raises(RepositoryLimitError):
        build_safe_manifest(tmp_path, limits=FileLimits(max_files=1))


def test_manifest_skips_symlinks(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("safe = True\n", encoding="utf-8")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlinks are not available in this environment")

    manifest = build_safe_manifest(tmp_path)

    assert {item.path for item in manifest.files} == {"target.py"}
    assert ("link.py", "symlink") in {
        (item.path, item.reason) for item in manifest.skipped
    }
