from __future__ import annotations

import subprocess

from hermes_semantic_diff_weaver.git_diff import GitRepository, collect_diff
from hermes_semantic_diff_weaver.models import WeaverConfig


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


def test_external_diff_driver_is_not_invoked(repo_factory) -> None:
    repo_path, base, head = repo_factory(
        {".gitattributes": "*.py diff=malicious\n", "a.py": "x = 1\n"},
        {".gitattributes": "*.py diff=malicious\n", "a.py": "x = 2\n"},
    )
    repo = GitRepository.open(str(repo_path))
    result = collect_diff(repo, base, head, WeaverConfig())
    assert [item.path for item in result.files] == ["a.py"]
