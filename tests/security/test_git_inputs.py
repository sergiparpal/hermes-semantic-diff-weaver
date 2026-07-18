from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes_semantic_diff_weaver.git_diff import GitRepository, collect_diff
from hermes_semantic_diff_weaver.models import WeaverConfig
from tests.conftest import git


def test_git_runner_never_uses_shell(repo_factory, monkeypatch) -> None:
    repo_path, base, head = repo_factory({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    real_run = subprocess.run
    observed: list[object] = []

    def spy(*args, **kwargs):
        observed.append(kwargs.get("shell"))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    collect_diff(GitRepository.open(str(repo_path)), base, head, WeaverConfig())
    assert observed and all(value is False for value in observed)


def test_git_runner_disables_global_config_attributes_and_paging(repo_factory, monkeypatch) -> None:
    repo_path, base, head = repo_factory({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    real_run = subprocess.run
    observed: list[tuple[list[str], dict[str, str]]] = []

    def spy(*args, **kwargs):
        observed.append((args[0], kwargs["env"]))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    collect_diff(GitRepository.open(str(repo_path)), base, head, WeaverConfig())
    assert observed
    for command, environment in observed:
        assert command[1] == "--no-pager"
        assert environment["GIT_ATTR_NOSYSTEM"] == "1"
        assert environment["GIT_CONFIG_GLOBAL"]
        assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
        assert environment["GIT_PAGER"] == "cat"


def test_external_diff_driver_is_not_invoked(repo_factory) -> None:
    repo_path, base, head = repo_factory(
        {".gitattributes": "*.py diff=malicious\n", "a.py": "x = 1\n"},
        {".gitattributes": "*.py diff=malicious\n", "a.py": "x = 2\n"},
    )
    repo = GitRepository.open(str(repo_path))
    result = collect_diff(repo, base, head, WeaverConfig())
    assert [item.path for item in result.files] == ["a.py"]


def test_committed_symlink_is_metadata_and_is_not_read(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Semantic Diff Tests")
    link = repo / "outside.py"
    try:
        link.symlink_to("../first-secret.py")
    except OSError:
        pytest.skip("symlink creation is unavailable")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    link.unlink()
    link.symlink_to("../second-secret.py")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "-m", "head")
    head = git(repo, "rev-parse", "HEAD")
    result = collect_diff(GitRepository.open(str(repo)), base, head, WeaverConfig())
    assert result.files == []
    assert result.excluded_counts["symlink_or_gitlink"] == 1


def test_newline_filename_is_parsed_without_record_corruption(repo_factory) -> None:
    path = "src/line\nbreak.py"
    repo, base, head = repo_factory(
        {path: "def f(x):\n    return x < 1\n"},
        {path: "def f(x):\n    return x <= 1\n"},
    )
    result = collect_diff(GitRepository.open(str(repo)), base, head, WeaverConfig())
    assert [item.path for item in result.files] == [path]
