"""Safe, bounded collection of committed Git diff data."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ErrorCode, WeaverError
from .models import WeaverConfig
from .path_policy import exclusion_reason, is_included, normalize_repo_path

GIT_TIMEOUT_SECONDS = 15
MAX_GIT_OUTPUT_BYTES = 16 * 1024 * 1024
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Hunk:
    id: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass
class ChangedFile:
    status: str
    old_path: str | None
    new_path: str | None
    additions: int = 0
    deletions: int = 0
    binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    old_text: str | None = None
    new_text: str | None = None
    parser_warning: str | None = None

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""


@dataclass
class DiffCollection:
    files: list[ChangedFile]
    changed_files_total: int
    changed_lines: int
    excluded_counts: dict[str, int]
    warnings: list[str]


def _git_error(code: ErrorCode, message: str, remediation: str) -> WeaverError:
    return WeaverError(code, message, remediation)


class GitRepository:
    """A Git repository boundary with a safe command runner."""

    def __init__(self, root: Path, git: str) -> None:
        self.root = root
        self.git = git

    @classmethod
    def open(cls, repo_path: str) -> GitRepository:
        git = shutil.which("git")
        if git is None:
            raise _git_error(
                ErrorCode.NOT_A_GIT_REPOSITORY,
                "Git is not available on PATH.",
                "Install Git and ensure the git executable is available on PATH.",
            )
        try:
            requested = Path(repo_path).resolve(strict=True)
        except OSError as exc:
            raise _git_error(
                ErrorCode.NOT_A_GIT_REPOSITORY,
                "The repository path does not exist or is inaccessible.",
                "Provide a readable local Git repository path.",
            ) from exc
        cwd = requested if requested.is_dir() else requested.parent
        probe = cls(cwd, git)
        try:
            raw_root = probe.run(["rev-parse", "--show-toplevel"], max_bytes=64 * 1024).strip()
            root = Path(raw_root).resolve(strict=True)
            requested.relative_to(root)
        except (OSError, ValueError, WeaverError) as exc:
            raise _git_error(
                ErrorCode.NOT_A_GIT_REPOSITORY,
                "The supplied path is not contained in a readable Git repository.",
                "Provide the repository root or a path inside a local Git repository.",
            ) from exc
        if root == Path(root.anchor):
            raise _git_error(
                ErrorCode.PATH_OUTSIDE_REPOSITORY,
                "A filesystem root may not be used as the repository boundary.",
                "Provide a bounded Git repository directory.",
            )
        return cls(root, git)

    def run(
        self,
        arguments: list[str],
        *,
        max_bytes: int = MAX_GIT_OUTPUT_BYTES,
        binary: bool = False,
    ) -> str | bytes:
        env = os.environ.copy()
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "LC_ALL": "C.UTF-8",
            }
        )
        command = [self.git, "-c", "core.quotepath=false", *arguments]
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                env=env,
                shell=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise _git_error(
                ErrorCode.NOT_A_GIT_REPOSITORY,
                "Git did not complete safely within the configured timeout.",
                "Verify the repository and Git installation, then retry with a smaller scope.",
            ) from exc
        if len(completed.stdout) > max_bytes or len(completed.stderr) > max_bytes:
            raise _git_error(
                ErrorCode.DIFF_TOO_LARGE,
                "Git output exceeded the bounded collection limit.",
                "Narrow the include patterns or split the change.",
            )
        if completed.returncode != 0:
            raise _git_error(
                ErrorCode.INVALID_REF,
                "Git could not resolve the requested revision or diff.",
                "Check that both refs exist locally and identify commits in this repository.",
            )
        if binary:
            return completed.stdout
        try:
            return completed.stdout.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise _git_error(
                ErrorCode.PARSE_FAILURE,
                "Git returned metadata that is not valid UTF-8.",
                "Rename the affected path to valid UTF-8 or narrow the analyzed scope.",
            ) from exc

    def resolve_ref(self, raw_ref: str) -> str:
        if (
            not raw_ref
            or raw_ref.startswith("-")
            or "\x00" in raw_ref
            or "\r" in raw_ref
            or "\n" in raw_ref
        ):
            raise _git_error(
                ErrorCode.INVALID_REF,
                "An empty or option-like Git ref was rejected.",
                "Provide a local branch, tag, or commit identifier that does not begin with '-'.",
            )
        try:
            resolved = self.run(
                ["rev-parse", "--verify", "--end-of-options", f"{raw_ref}^{{commit}}"],
                max_bytes=1024,
            ).strip()
        except WeaverError as exc:
            raise _git_error(
                ErrorCode.INVALID_REF,
                "A requested Git ref does not resolve to a commit.",
                "Check that the base and head refs exist locally and name commits.",
            ) from exc
        if not COMMIT_RE.fullmatch(resolved):
            raise _git_error(
                ErrorCode.INVALID_REF,
                "Git returned an invalid commit identifier.",
                "Verify repository integrity and retry.",
            )
        return resolved

    def read_blob(self, commit: str, path: str, max_bytes: int) -> str | None:
        if not COMMIT_RE.fullmatch(commit):
            raise _git_error(ErrorCode.INVALID_REF, "An unresolved commit was rejected.", "Retry.")
        normalized = normalize_repo_path(path)
        try:
            size_text = self.run(["cat-file", "-s", f"{commit}:{normalized}"], max_bytes=1024)
            size = int(size_text.strip())
        except (ValueError, WeaverError):
            return None
        if size > max_bytes:
            return None
        try:
            raw = self.run(["show", f"{commit}:{normalized}"], max_bytes=max_bytes, binary=True)
        except WeaverError:
            return None
        if b"\x00" in raw:
            return None
        try:
            return raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None

    def list_files(self, commit: str, max_bytes: int = MAX_GIT_OUTPUT_BYTES) -> list[str]:
        raw = self.run(
            ["ls-tree", "-r", "-z", "--name-only", commit, "--"],
            max_bytes=max_bytes,
            binary=True,
        )
        result: list[str] = []
        for item in raw.split(b"\x00"):
            if not item:
                continue
            try:
                result.append(normalize_repo_path(item.decode("utf-8", errors="strict")))
            except (UnicodeDecodeError, WeaverError):
                continue
        return result


def _parse_name_status(raw: bytes) -> list[ChangedFile]:
    fields = raw.split(b"\x00")
    files: list[ChangedFile] = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index].decode("ascii", errors="strict")
        index += 1
        code = status[:1]
        if code in {"R", "C"}:
            old_path = normalize_repo_path(fields[index].decode("utf-8", errors="strict"))
            new_path = normalize_repo_path(fields[index + 1].decode("utf-8", errors="strict"))
            index += 2
        else:
            path = normalize_repo_path(fields[index].decode("utf-8", errors="strict"))
            index += 1
            old_path = None if code == "A" else path
            new_path = None if code == "D" else path
        files.append(ChangedFile(status=status, old_path=old_path, new_path=new_path))
    return files


def _parse_numstat(raw: bytes) -> tuple[dict[str, tuple[int, int, bool]], int]:
    stats: dict[str, tuple[int, int, bool]] = {}
    total = 0
    fields = raw.split(b"\x00")
    index = 0
    while index < len(fields) and fields[index]:
        record = fields[index]
        index += 1
        pieces = record.split(b"\t", 2)
        if len(pieces) != 3:
            continue
        add_raw, delete_raw, path_raw = pieces
        binary = add_raw == b"-" or delete_raw == b"-"
        additions = 0 if binary else int(add_raw)
        deletions = 0 if binary else int(delete_raw)
        if path_raw:
            path = normalize_repo_path(path_raw.decode("utf-8", errors="strict"))
        else:
            if index + 1 >= len(fields):
                break
            index += 1
            path = normalize_repo_path(fields[index].decode("utf-8", errors="strict"))
            index += 1
        stats[path] = (additions, deletions, binary)
        total += additions + deletions
    return stats, total


def _hunks(repo: GitRepository, base: str, head: str, path: str) -> list[Hunk]:
    output = repo.run(
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--unified=0",
            base,
            head,
            "--",
            path,
        ],
        max_bytes=4 * 1024 * 1024,
    )
    result: list[Hunk] = []
    for line in output.splitlines():
        match = HUNK_RE.match(line)
        if match:
            result.append(
                Hunk(
                    id=f"hunk-{len(result) + 1:03d}",
                    old_start=int(match.group(1)),
                    old_count=int(match.group(2) or 1),
                    new_start=int(match.group(3)),
                    new_count=int(match.group(4) or 1),
                )
            )
    return result


def collect_diff(
    repo: GitRepository,
    base_commit: str,
    head_commit: str,
    config: WeaverConfig,
) -> DiffCollection:
    """Collect bounded changed Python blobs without checking out or executing code."""
    name_raw = repo.run(
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-status",
            "-z",
            "-M",
            "-C",
            base_commit,
            head_commit,
            "--",
        ],
        binary=True,
    )
    files = _parse_name_status(name_raw)
    if len(files) > config.rules.max_changed_files:
        raise _git_error(
            ErrorCode.DIFF_TOO_LARGE,
            f"The diff contains {len(files)} changed files; the configured limit is "
            f"{config.rules.max_changed_files}.",
            "Narrow the include patterns, split the change, or increase rules.max_changed_files.",
        )
    numstat_raw = repo.run(
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--numstat",
            "-z",
            base_commit,
            head_commit,
            "--",
        ],
        binary=True,
    )
    stats, changed_lines = _parse_numstat(numstat_raw)
    if changed_lines > config.rules.max_diff_lines:
        raise _git_error(
            ErrorCode.DIFF_TOO_LARGE,
            f"The diff contains {changed_lines} changed lines; the configured limit is "
            f"{config.rules.max_diff_lines}.",
            "Narrow the include patterns, split the change, or increase rules.max_diff_lines.",
        )
    excluded: Counter[str] = Counter()
    selected: list[ChangedFile] = []
    warnings: list[str] = []
    for changed in files:
        path = changed.path
        reason = exclusion_reason(path)
        if reason:
            excluded[reason] += 1
            continue
        if not is_included(path, config.paths.include, config.paths.exclude):
            excluded["path_filter"] += 1
            continue
        if not path.endswith(".py"):
            excluded["unsupported_extension"] += 1
            continue
        additions, deletions, binary = stats.get(path, (0, 0, False))
        changed.additions = additions
        changed.deletions = deletions
        changed.binary = binary
        if binary:
            excluded["binary"] += 1
            continue
        changed.hunks = _hunks(repo, base_commit, head_commit, path)
        if changed.old_path:
            changed.old_text = repo.read_blob(
                base_commit, changed.old_path, config.rules.max_file_bytes
            )
        if changed.new_path:
            changed.new_text = repo.read_blob(
                head_commit, changed.new_path, config.rules.max_file_bytes
            )
        if (changed.old_path and changed.old_text is None) or (
            changed.new_path and changed.new_text is None
        ):
            excluded["oversized_or_non_utf8"] += 1
            warnings.append(f"Skipped bounded source parsing for {path!r}.")
            continue
        selected.append(changed)
    return DiffCollection(
        files=selected,
        changed_files_total=len(files),
        changed_lines=changed_lines,
        excluded_counts=dict(sorted(excluded.items())),
        warnings=warnings,
    )
