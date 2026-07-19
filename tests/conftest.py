from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


def git(repo: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        pytest.skip("Git is unavailable")
    completed = subprocess.run(
        [executable, *arguments],
        cwd=repo,
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="strict",
        shell=False,
    )
    return completed.stdout.strip()


@pytest.fixture
def repo_factory(tmp_path: Path) -> Callable[..., tuple[Path, str, str]]:
    counter = 0

    def create(
        old_files: dict[str, str],
        new_files: dict[str, str],
        *,
        remove: tuple[str, ...] = (),
    ) -> tuple[Path, str, str]:
        nonlocal counter
        counter += 1
        repo = tmp_path / f"repo-{counter}"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "tests@example.invalid")
        git(repo, "config", "user.name", "Semantic Diff Tests")
        git(repo, "config", "core.autocrlf", "false")
        for relative, text in old_files.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        git(repo, "add", "--all")
        git(repo, "commit", "-q", "-m", "base")
        base = git(repo, "rev-parse", "HEAD")
        for relative in remove:
            path = repo / relative
            if path.exists():
                path.unlink()
        for relative, text in new_files.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        git(repo, "add", "--all")
        git(repo, "commit", "-q", "-m", "head")
        head = git(repo, "rev-parse", "HEAD")
        return repo, base, head

    return create
