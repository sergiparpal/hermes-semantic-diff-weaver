from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_semantic_diff_weaver.errors import ErrorCode, WeaverError
from hermes_semantic_diff_weaver.git_diff import GitRepository, collect_diff
from hermes_semantic_diff_weaver.models import WeaverConfig


def test_open_resolve_and_collect(repo_factory) -> None:
    repo_path, base, head = repo_factory(
        {"src/api.py": "def allowed(x):\n    return x < 5\n"},
        {"src/api.py": "def allowed(x):\n    return x <= 5\n"},
    )
    repo = GitRepository.open(str(repo_path / "src"))
    assert repo.resolve_ref(base) == base
    assert repo.resolve_ref(head) == head
    result = collect_diff(repo, base, head, WeaverConfig())
    assert len(result.files) == 1
    assert result.files[0].old_text
    assert result.files[0].new_text
    assert result.files[0].hunks
    assert result.changed_lines == 2


@pytest.mark.parametrize("ref", ["--help", "-n", "bad\nref", ""])
def test_option_like_and_invalid_refs_are_rejected(repo_factory, ref: str) -> None:
    repo_path, _, _ = repo_factory({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    repo = GitRepository.open(str(repo_path))
    with pytest.raises(WeaverError) as caught:
        repo.resolve_ref(ref)
    assert caught.value.code is ErrorCode.INVALID_REF


def test_diff_limits_fail_with_safe_counts(repo_factory) -> None:
    repo_path, base, head = repo_factory(
        {"a.py": "x = 1\n"},
        {"a.py": "x = 2\ny = 3\n"},
    )
    config = WeaverConfig()
    config.rules.max_diff_lines = 1
    with pytest.raises(WeaverError) as caught:
        collect_diff(GitRepository.open(str(repo_path)), base, head, config)
    assert caught.value.code is ErrorCode.DIFF_TOO_LARGE
    assert "configured limit is 1" in caught.value.safe_message


def test_not_a_repository_is_safe(tmp_path: Path) -> None:
    with pytest.raises(WeaverError) as caught:
        GitRepository.open(str(tmp_path))
    assert caught.value.code is ErrorCode.NOT_A_GIT_REPOSITORY


def test_missing_git_is_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(WeaverError) as caught:
        GitRepository.open(str(tmp_path))
    assert caught.value.code is ErrorCode.NOT_A_GIT_REPOSITORY


def test_nonexistent_ref_and_blob_paths_are_bounded(repo_factory) -> None:
    repo_path, _, head = repo_factory({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    repo = GitRepository.open(str(repo_path))
    with pytest.raises(WeaverError) as caught:
        repo.resolve_ref("does-not-exist")
    assert caught.value.code is ErrorCode.INVALID_REF
    assert repo.read_blob(head, "missing.py", 100) is None
    assert "a.py" in repo.list_files(head)


def test_git_output_and_decode_limits_are_safe(tmp_path: Path, monkeypatch) -> None:
    repo = GitRepository(tmp_path, "git")

    def huge(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout=b"x" * 20, stderr=b"")

    monkeypatch.setattr(subprocess, "run", huge)
    with pytest.raises(WeaverError) as caught:
        repo.run(["status"], max_bytes=10)
    assert caught.value.code is ErrorCode.DIFF_TOO_LARGE

    def invalid_utf8(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout=b"\xff", stderr=b"")

    monkeypatch.setattr(subprocess, "run", invalid_utf8)
    with pytest.raises(WeaverError) as decode_error:
        repo.run(["status"])
    assert decode_error.value.code is ErrorCode.PARSE_FAILURE
