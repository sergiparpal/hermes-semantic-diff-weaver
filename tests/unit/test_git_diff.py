from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_semantic_diff_weaver.errors import ErrorCode, WeaverError
from hermes_semantic_diff_weaver.git_diff import (
    GitRepository,
    _parse_name_status,
    _parse_numstat,
    collect_diff,
)
from hermes_semantic_diff_weaver.models import CriticalPath, WeaverConfig


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


def test_crlf_move_and_rename_is_correlated(repo_factory) -> None:
    repo_path, base, head = repo_factory(
        {"src/old.py": "def old_name(x):\r\n    return x + 1\r\n"},
        {"src/new.py": "def new_name(x):\r\n    return x + 1\r\n"},
        remove=("src/old.py",),
    )
    result = collect_diff(GitRepository.open(str(repo_path)), base, head, WeaverConfig())
    assert len(result.files) == 1
    assert result.files[0].status.startswith("R")
    assert result.files[0].old_path == "src/old.py"
    assert result.files[0].new_path == "src/new.py"
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


def test_oversized_diff_can_prioritize_explicit_critical_scope(repo_factory) -> None:
    repo_path, base, head = repo_factory(
        {"critical.py": "x = 1\n", "other.py": "y = 1\n"},
        {"critical.py": "x = 2\n", "other.py": "y = 2\n"},
    )
    config = WeaverConfig(critical_paths=[CriticalPath(pattern="critical.py", weight=100)])
    config.rules.max_changed_files = 1
    config.rules.max_diff_lines = 2
    result = collect_diff(GitRepository.open(str(repo_path)), base, head, config)
    assert [item.path for item in result.files] == ["critical.py"]
    assert result.truncated is True
    assert result.omitted_counts == {"resource_prioritization": 1}


def test_secret_source_of_a_rename_remains_excluded(repo_factory) -> None:
    source = "def value():\n    return 1\n"
    repo_path, base, head = repo_factory(
        {".env": source},
        {"safe.py": source},
        remove=(".env",),
    )
    result = collect_diff(GitRepository.open(str(repo_path)), base, head, WeaverConfig())
    assert result.files == []
    assert result.excluded_counts["secret_filename"] >= 1


def test_blob_and_tree_edge_cases_are_bounded(tmp_path: Path, monkeypatch) -> None:
    repo = GitRepository(tmp_path, "git")
    commit = "a" * 40
    with pytest.raises(WeaverError):
        repo.read_blob("unresolved", "a.py", 100)
    with pytest.raises(WeaverError):
        repo.entry_mode("unresolved", "a.py")

    monkeypatch.setattr(repo, "run", lambda *args, **kwargs: "200")
    assert repo.read_blob(commit, "a.py", 100) is None

    def nul_blob(arguments, **kwargs):
        return "2" if arguments[0] == "cat-file" else b"\x00x"

    monkeypatch.setattr(repo, "run", nul_blob)
    assert repo.read_blob(commit, "a.py", 100) is None

    def invalid_blob(arguments, **kwargs):
        return "1" if arguments[0] == "cat-file" else b"\xff"

    monkeypatch.setattr(repo, "run", invalid_blob)
    assert repo.read_blob(commit, "a.py", 100) is None

    def failed_show(arguments, **kwargs):
        if arguments[0] == "cat-file":
            return "1"
        raise WeaverError(ErrorCode.INVALID_REF, "safe", "retry")

    monkeypatch.setattr(repo, "run", failed_show)
    assert repo.read_blob(commit, "a.py", 100) is None

    monkeypatch.setattr(repo, "run", lambda *args, **kwargs: b"")
    assert repo.entry_mode(commit, "a.py") is None
    monkeypatch.setattr(repo, "run", lambda *args, **kwargs: b"invalid\x00")
    assert repo.entry_mode(commit, "a.py") is None
    monkeypatch.setattr(
        repo,
        "run",
        lambda *args, **kwargs: b"\xff blob aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\ta.py\x00",
    )
    assert repo.entry_mode(commit, "a.py") is None

    def failed_tree(*args, **kwargs):
        raise WeaverError(ErrorCode.INVALID_REF, "safe", "retry")

    monkeypatch.setattr(repo, "run", failed_tree)
    assert repo.entry_mode(commit, "a.py") is None
    monkeypatch.setattr(repo, "run", lambda *args, **kwargs: b"../bad\x00good.py\x00\xff\x00")
    assert repo.list_files(commit) == ["good.py"]


def test_malformed_and_truncated_numstat_records_are_ignored() -> None:
    assert _parse_numstat(b"malformed\x00") == ({}, 0)
    assert _parse_numstat(b"1\t1\t\x00") == ({}, 0)


def test_nul_delimited_metadata_preserves_newline_filename() -> None:
    path = "src/line\nbreak.py"
    changed = _parse_name_status(b"M\x00" + path.encode("utf-8") + b"\x00")
    assert len(changed) == 1
    assert changed[0].old_path == path
    assert changed[0].new_path == path
    assert _parse_numstat(b"1\t1\t" + path.encode("utf-8") + b"\x00") == (
        {path: (1, 1, False)},
        2,
    )


def test_critical_prioritization_requires_a_match_and_respects_line_budget(
    repo_factory,
) -> None:
    repo_path, base, head = repo_factory(
        {"critical.py": "x = 1\n", "other.py": "y = 1\n"},
        {"critical.py": "x = 2\n", "other.py": "y = 2\n"},
    )
    repo = GitRepository.open(str(repo_path))
    no_match = WeaverConfig(critical_paths=[CriticalPath(pattern="missing.py", weight=100)])
    no_match.rules.max_changed_files = 1
    with pytest.raises(WeaverError):
        collect_diff(repo, base, head, no_match)

    line_budget = WeaverConfig(critical_paths=[CriticalPath(pattern="critical.py", weight=100)])
    line_budget.rules.max_changed_files = 2
    line_budget.rules.max_diff_lines = 2
    result = collect_diff(repo, base, head, line_budget)
    assert [item.path for item in result.files] == ["critical.py"]


def test_unsupported_and_oversized_sources_are_explicitly_excluded(repo_factory) -> None:
    repo_path, base, head = repo_factory({"README.md": "old\n"}, {"README.md": "new\n"})
    config = WeaverConfig()
    config.paths.include = ["**/*"]
    unsupported = collect_diff(GitRepository.open(str(repo_path)), base, head, config)
    assert unsupported.excluded_counts["unsupported_extension"] == 1

    large = "value = '" + "x" * 2000 + "'\n"
    large_repo, large_base, large_head = repo_factory(
        {"large.py": large.replace("x", "y")}, {"large.py": large}
    )
    size_config = WeaverConfig()
    size_config.rules.max_file_bytes = 1024
    oversized = collect_diff(
        GitRepository.open(str(large_repo)), large_base, large_head, size_config
    )
    assert oversized.files == []
    assert oversized.excluded_counts["oversized_or_non_utf8"] == 1
