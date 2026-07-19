"""Safe, bounded collection of committed Git diff data."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Literal, overload

from .errors import ErrorCode, WeaverError
from .models import WeaverConfig
from .path_policy import exclusion_reason, glob_matches, is_included, normalize_repo_path

GIT_TIMEOUT_SECONDS = 15
MAX_GIT_OUTPUT_BYTES = 16 * 1024 * 1024
HARD_MAX_GIT_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_GIT_INPUT_BYTES = 2 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BLOB_BYTES = 64 * 1024 * 1024
MAX_ANALYZED_FILES = 1000
MAX_TREE_PATHS_PER_COMMAND = 256
# Git's 50% default misses small CRLF renames; AST matching still rejects ambiguous symbols.
RENAME_DETECTION_ARGUMENTS = ("-M40%", "-C40%")
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
    omitted_counts: dict[str, int] = field(default_factory=dict)
    truncated: bool = False


@dataclass(frozen=True)
class GitTreeEntry:
    mode: str
    object_id: str


@dataclass
class _BlobBatch:
    texts: dict[str, str | None]
    failures: dict[str, str]


class _OutputLimitExceeded(Exception):
    pass


def _git_error(code: ErrorCode, message: str, remediation: str) -> WeaverError:
    return WeaverError(code, message, remediation)


def _run_bounded_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    input_data: bytes | None,
    max_bytes: int,
) -> subprocess.CompletedProcess[bytes]:
    """Drain both pipes concurrently and stop the child as soon as either cap is exceeded."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        shell=False,
        stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()
    reader_errors: list[OSError] = []

    def drain(stream: BinaryIO, destination: bytearray) -> None:
        try:
            while chunk := stream.read(64 * 1024):
                remaining = max_bytes - len(destination)
                if len(chunk) > remaining:
                    destination.extend(chunk[: max(0, remaining)])
                    overflow.set()
                    process.kill()
                    return
                destination.extend(chunk)
        except OSError as exc:
            reader_errors.append(exc)

    assert process.stdout is not None
    assert process.stderr is not None
    readers = [
        threading.Thread(target=drain, args=(process.stdout, stdout), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, stderr), daemon=True),
    ]
    for thread in readers:
        thread.start()

    writer: threading.Thread | None = None
    if input_data is not None:
        assert process.stdin is not None
        process_stdin = process.stdin

        def write_input() -> None:
            try:
                process_stdin.write(input_data)
                process_stdin.close()
            except BrokenPipeError:
                pass
            except OSError as exc:
                reader_errors.append(exc)

        writer = threading.Thread(target=write_input, daemon=True)
        writer.start()

    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        while process.poll() is None:
            if overflow.is_set():
                process.kill()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                raise subprocess.TimeoutExpired(command, GIT_TIMEOUT_SECONDS)
            try:
                process.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for thread in readers:
            thread.join(timeout=1)
        if writer is not None:
            writer.join(timeout=1)
    if overflow.is_set():
        raise _OutputLimitExceeded
    if reader_errors:
        raise reader_errors[0]
    return subprocess.CompletedProcess(command, process.returncode, bytes(stdout), bytes(stderr))


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

    @overload
    def run(
        self,
        arguments: list[str],
        *,
        max_bytes: int = MAX_GIT_OUTPUT_BYTES,
        binary: Literal[False] = False,
        input_data: bytes | None = None,
    ) -> str: ...

    @overload
    def run(
        self,
        arguments: list[str],
        *,
        max_bytes: int = MAX_GIT_OUTPUT_BYTES,
        binary: Literal[True],
        input_data: bytes | None = None,
    ) -> bytes: ...

    def run(
        self,
        arguments: list[str],
        *,
        max_bytes: int = MAX_GIT_OUTPUT_BYTES,
        binary: bool = False,
        input_data: bytes | None = None,
    ) -> str | bytes:
        env = os.environ.copy()
        env.update(
            {
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_PAGER": "cat",
                "LC_ALL": "C.UTF-8",
            }
        )
        command = [self.git, "--no-pager", "-c", "core.quotepath=false", *arguments]
        if input_data is not None and len(input_data) > MAX_GIT_INPUT_BYTES:
            raise _git_error(
                ErrorCode.DIFF_TOO_LARGE,
                "Git input exceeded the bounded collection limit.",
                "Narrow the include patterns or split the change.",
            )
        try:
            completed = _run_bounded_process(
                command,
                cwd=self.root,
                env=env,
                input_data=input_data,
                max_bytes=min(max_bytes, HARD_MAX_GIT_OUTPUT_BYTES),
            )
        except _OutputLimitExceeded as exc:
            raise _git_error(
                ErrorCode.DIFF_TOO_LARGE,
                "Git output exceeded the bounded collection limit.",
                "Narrow the include patterns or split the change.",
            ) from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise _git_error(
                ErrorCode.NOT_A_GIT_REPOSITORY,
                "Git did not complete safely within the configured timeout.",
                "Verify the repository and Git installation, then retry with a smaller scope.",
            ) from exc
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
        effective_max_bytes = min(max_bytes, MAX_SOURCE_FILE_BYTES)
        if size > effective_max_bytes:
            return None
        try:
            raw = self.run(
                ["show", f"{commit}:{normalized}"],
                max_bytes=effective_max_bytes,
                binary=True,
            )
        except WeaverError:
            return None
        if b"\x00" in raw:
            return None
        try:
            return raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None

    def entry_mode(self, commit: str, path: str) -> str | None:
        """Return the committed Git mode without following symlinks or Git links."""
        if not COMMIT_RE.fullmatch(commit):
            raise _git_error(ErrorCode.INVALID_REF, "An unresolved commit was rejected.", "Retry.")
        normalized = normalize_repo_path(path)
        try:
            raw = self.run(
                ["ls-tree", "-z", commit, "--", normalized],
                max_bytes=64 * 1024,
                binary=True,
            )
        except WeaverError:
            return None
        if not raw:
            return None
        header = raw.split(b"\t", 1)[0]
        parts = header.split(b" ", 2)
        if len(parts) != 3:
            return None
        try:
            return parts[0].decode("ascii", errors="strict")
        except UnicodeDecodeError:
            return None

    def tree_entries(self, commit: str, paths: list[str]) -> dict[str, GitTreeEntry]:
        """Read modes and object IDs for literal committed paths in one bounded command."""
        if not COMMIT_RE.fullmatch(commit):
            raise _git_error(ErrorCode.INVALID_REF, "An unresolved commit was rejected.", "Retry.")
        normalized_paths = sorted({normalize_repo_path(path) for path in paths})
        if not normalized_paths:
            return {}
        requested = set(normalized_paths)
        entries: dict[str, GitTreeEntry] = {}
        for start in range(0, len(normalized_paths), MAX_TREE_PATHS_PER_COMMAND):
            chunk = normalized_paths[start : start + MAX_TREE_PATHS_PER_COMMAND]
            raw = self.run(
                [
                    "ls-tree",
                    "-z",
                    commit,
                    "--",
                    *(f":(literal){path}" for path in chunk),
                ],
                binary=True,
            )
            for record in raw.split(b"\x00"):
                if not record or b"\t" not in record:
                    continue
                header, path_raw = record.split(b"\t", 1)
                parts = header.split(b" ", 2)
                if len(parts) != 3:
                    continue
                try:
                    mode = parts[0].decode("ascii", errors="strict")
                    object_id = parts[2].decode("ascii", errors="strict")
                    path = normalize_repo_path(path_raw.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, WeaverError):
                    continue
                if path in requested and COMMIT_RE.fullmatch(object_id):
                    entries[path] = GitTreeEntry(mode=mode, object_id=object_id)
        return entries

    def read_blob_objects(
        self,
        object_ids: set[str],
        max_bytes: int,
        *,
        max_total_bytes: int = MAX_SOURCE_BLOB_BYTES,
    ) -> dict[str, str | None]:
        """Read many bounded blob objects with batch plumbing instead of per-file processes."""
        return self._read_blob_objects(object_ids, max_bytes, max_total_bytes=max_total_bytes).texts

    def _read_blob_objects(
        self,
        object_ids: set[str],
        max_bytes: int,
        *,
        max_total_bytes: int = MAX_SOURCE_BLOB_BYTES,
    ) -> _BlobBatch:
        """Return bounded blob text plus non-sensitive failure classes for scope reporting."""
        requested = sorted(object_ids)
        if any(not COMMIT_RE.fullmatch(object_id) for object_id in requested):
            raise _git_error(ErrorCode.INVALID_REF, "An invalid object ID was rejected.", "Retry.")
        result: dict[str, str | None] = dict.fromkeys(requested)
        failures = dict.fromkeys(requested, "missing_or_not_blob")
        if not requested:
            return _BlobBatch(result, failures)
        batch_input = b"".join(f"{object_id}\n".encode("ascii") for object_id in requested)
        try:
            raw_info = self.run(
                ["cat-file", "--batch-check"],
                max_bytes=max(1024, len(requested) * 128),
                binary=True,
                input_data=batch_input,
            )
        except WeaverError:
            return _BlobBatch(result, failures)
        eligible: list[tuple[str, int]] = []
        aggregate_bytes = 0
        effective_max_bytes = min(max_bytes, MAX_SOURCE_FILE_BYTES)
        for line in raw_info.splitlines():
            parts = line.split(b" ")
            if len(parts) != 3 or parts[1] != b"blob":
                continue
            try:
                object_id = parts[0].decode("ascii", errors="strict")
                size = int(parts[2])
            except (UnicodeDecodeError, ValueError):
                continue
            if object_id not in result or size < 0:
                continue
            if size > effective_max_bytes:
                failures[object_id] = "oversized"
                continue
            if aggregate_bytes + size > min(max_total_bytes, MAX_SOURCE_BLOB_BYTES):
                failures[object_id] = "aggregate_source_limit"
                continue
            eligible.append((object_id, size))
            aggregate_bytes += size

        chunk_budget = MAX_GIT_OUTPUT_BYTES
        chunks: list[list[tuple[str, int]]] = []
        current: list[tuple[str, int]] = []
        current_bytes = 0
        for object_id, size in eligible:
            estimated_bytes = size + len(object_id) + 32
            if current and current_bytes + estimated_bytes > chunk_budget:
                chunks.append(current)
                current = []
                current_bytes = 0
            current.append((object_id, size))
            current_bytes += estimated_bytes
        if current:
            chunks.append(current)

        for chunk in chunks:
            chunk_input = b"".join(f"{object_id}\n".encode("ascii") for object_id, _ in chunk)
            expected_bytes = sum(size + len(object_id) + 32 for object_id, size in chunk)
            try:
                raw_blobs = self.run(
                    ["cat-file", "--batch"],
                    max_bytes=max(1024, expected_bytes),
                    binary=True,
                    input_data=chunk_input,
                )
            except WeaverError:
                continue
            offset = 0
            while offset < len(raw_blobs):
                header_end = raw_blobs.find(b"\n", offset)
                if header_end < 0:
                    break
                header = raw_blobs[offset:header_end].split(b" ")
                if len(header) != 3 or header[1] != b"blob":
                    break
                try:
                    object_id = header[0].decode("ascii", errors="strict")
                    size = int(header[2])
                except (UnicodeDecodeError, ValueError):
                    break
                content_start = header_end + 1
                content_end = content_start + size
                if (
                    content_end >= len(raw_blobs)
                    or raw_blobs[content_end : content_end + 1] != b"\n"
                ):
                    break
                content = raw_blobs[content_start:content_end]
                offset = content_end + 1
                if object_id not in result:
                    continue
                if b"\x00" in content:
                    failures[object_id] = "binary"
                    continue
                try:
                    result[object_id] = content.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    failures[object_id] = "non_utf8"
                    continue
                failures.pop(object_id, None)
        return _BlobBatch(result, failures)

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
        old_path: str | None
        new_path: str | None
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
            "--text",
            "--unified=0",
            base,
            head,
            "--",
            f":(literal){path}",
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


def _critical_weight(path: str, config: WeaverConfig) -> int:
    return max(
        (item.weight for item in config.critical_paths if glob_matches(path, item.pattern)),
        default=0,
    )


def _resource_selection(
    files: list[ChangedFile],
    stats: dict[str, tuple[int, int, bool]],
    changed_lines: int,
    config: WeaverConfig,
) -> tuple[set[str] | None, dict[str, int], list[str]]:
    """Prioritize bounded critical-path scope after mandatory and user filtering."""
    file_limit = min(config.rules.max_changed_files, MAX_ANALYZED_FILES)
    files_exceeded = len(files) > file_limit
    lines_exceeded = changed_lines > config.rules.max_diff_lines
    if not files_exceeded and not lines_exceeded:
        return None, {}, []
    if not config.critical_paths:
        if files_exceeded:
            raise _git_error(
                ErrorCode.DIFF_TOO_LARGE,
                f"The diff contains {len(files)} changed files; the configured limit is "
                f"{file_limit}.",
                "Narrow the include patterns, split the change, or increase "
                "rules.max_changed_files.",
            )
        raise _git_error(
            ErrorCode.DIFF_TOO_LARGE,
            f"The diff contains {changed_lines} changed lines; the configured limit is "
            f"{config.rules.max_diff_lines}.",
            "Narrow the include patterns, split the change, or increase rules.max_diff_lines.",
        )
    ranked = sorted(
        files,
        key=lambda item: (
            -_critical_weight(item.path, config),
            -sum(stats.get(item.path, (0, 0, False))[:2]),
            item.path,
        ),
    )
    if not ranked or _critical_weight(ranked[0].path, config) == 0:
        raise _git_error(
            ErrorCode.DIFF_TOO_LARGE,
            "The diff exceeds configured limits and no bounded critical-path scope can be selected.",
            "Narrow the include patterns, split the change, or configure a matching critical path.",
        )
    selected: set[str] = set()
    selected_lines = 0
    for changed in ranked:
        if len(selected) >= file_limit:
            break
        additions, deletions, _ = stats.get(changed.path, (0, 0, False))
        file_lines = additions + deletions
        if file_lines > config.rules.max_diff_lines and _critical_weight(changed.path, config):
            raise _git_error(
                ErrorCode.DIFF_TOO_LARGE,
                "A prioritized critical-path file exceeds the configured changed-line limit.",
                "Split the critical-path change or increase rules.max_diff_lines.",
            )
        if selected_lines + file_lines > config.rules.max_diff_lines:
            continue
        selected.add(changed.path)
        selected_lines += file_lines
    if not selected:
        raise _git_error(
            ErrorCode.DIFF_TOO_LARGE,
            "The diff exceeds configured limits and no file fits the bounded analysis scope.",
            "Narrow the include patterns or split the change.",
        )
    omitted = max(0, len(files) - len(selected))
    omitted_counts = {"resource_prioritization": omitted} if omitted else {}
    warnings = [
        "The diff exceeded global resource limits; analyzed prioritized critical-path scope only."
    ]
    return selected, omitted_counts, warnings


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
            *RENAME_DETECTION_ARGUMENTS,
            base_commit,
            head_commit,
            "--",
        ],
        binary=True,
    )
    files = _parse_name_status(name_raw)
    numstat_raw = repo.run(
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--text",
            "--numstat",
            "-z",
            *RENAME_DETECTION_ARGUMENTS,
            base_commit,
            head_commit,
            "--",
        ],
        binary=True,
    )
    stats, changed_lines = _parse_numstat(numstat_raw)
    excluded: Counter[str] = Counter()
    candidates: list[ChangedFile] = []
    selected: list[ChangedFile] = []
    warnings: list[str] = []
    for changed in files:
        path = changed.path
        reason = next(
            (
                current
                for candidate_path in (changed.old_path, changed.new_path)
                if candidate_path
                if (current := exclusion_reason(candidate_path))
            ),
            None,
        )
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
        candidates.append(changed)

    eligible_changed_lines = sum(item.additions + item.deletions for item in candidates)
    selected_scope, omitted_counts, resource_warnings = _resource_selection(
        candidates, stats, eligible_changed_lines, config
    )
    warnings.extend(resource_warnings)
    if selected_scope is not None:
        candidates = [item for item in candidates if item.path in selected_scope]

    base_entries = repo.tree_entries(
        base_commit,
        [item.old_path for item in candidates if item.old_path and not item.status.startswith("C")],
    )
    head_entries = repo.tree_entries(
        head_commit, [item.new_path for item in candidates if item.new_path]
    )
    object_ids = {
        entry.object_id
        for entries in (base_entries, head_entries)
        for entry in entries.values()
        if entry.mode not in {"120000", "160000"}
    }
    blob_batch = repo._read_blob_objects(object_ids, config.rules.max_file_bytes)
    source_truncated = False

    for changed in candidates:
        is_copy = changed.status.startswith("C")
        old_entry = base_entries.get(changed.old_path) if changed.old_path and not is_copy else None
        new_entry = head_entries.get(changed.new_path) if changed.new_path else None
        modes = {entry.mode for entry in (old_entry, new_entry) if entry is not None}
        if modes & {"120000", "160000"}:
            excluded["symlink_or_gitlink"] += 1
            continue
        changed.old_text = blob_batch.texts.get(old_entry.object_id) if old_entry else None
        changed.new_text = blob_batch.texts.get(new_entry.object_id) if new_entry else None
        if (changed.old_path and not is_copy and changed.old_text is None) or (
            changed.new_path and changed.new_text is None
        ):
            failure_classes = {
                blob_batch.failures.get(entry.object_id, "missing_or_not_blob")
                for entry in (old_entry, new_entry)
                if entry is not None and blob_batch.texts.get(entry.object_id) is None
            }
            if "binary" in failure_classes:
                excluded["binary"] += 1
            elif "aggregate_source_limit" in failure_classes:
                excluded["aggregate_source_limit"] += 1
                omitted_counts["aggregate_source_limit"] = (
                    omitted_counts.get("aggregate_source_limit", 0) + 1
                )
                source_truncated = True
            else:
                excluded["oversized_or_non_utf8"] += 1
            warnings.append(f"Skipped bounded source parsing for {changed.path!r}.")
            continue
        if is_copy:
            changed.hunks = [
                Hunk(
                    id="hunk-001",
                    old_start=0,
                    old_count=0,
                    new_start=1,
                    new_count=max(1, len((changed.new_text or "").splitlines())),
                )
            ]
        else:
            changed.hunks = _hunks(repo, base_commit, head_commit, changed.path)
        selected.append(changed)
    return DiffCollection(
        files=selected,
        changed_files_total=len(files),
        changed_lines=changed_lines,
        excluded_counts=dict(sorted(excluded.items())),
        warnings=warnings,
        omitted_counts=omitted_counts,
        truncated=selected_scope is not None or source_truncated,
    )
