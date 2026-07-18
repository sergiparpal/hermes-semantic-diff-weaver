from __future__ import annotations

from pathlib import Path

import pytest

from hermes_semantic_diff_weaver.errors import WeaverError
from hermes_semantic_diff_weaver.path_policy import (
    ensure_contained,
    exclusion_reason,
    glob_matches,
    normalize_repo_path,
    redact_text,
)


@pytest.mark.parametrize(
    "path",
    ["../escape.py", "/etc/passwd", "C:\\outside\\file.py", ".git/config", "line\nbreak.py"],
)
def test_untrusted_paths_are_rejected(path: str) -> None:
    with pytest.raises(WeaverError):
        normalize_repo_path(path)


def test_paths_normalize_and_globs_match_root() -> None:
    assert normalize_repo_path("src\\api.py") == "src/api.py"
    assert glob_matches("api.py", "**/*.py")
    assert glob_matches("src/api.py", "**/*.py")


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (".env.production", "secret_filename"),
        ("keys/id_rsa", "secret_filename"),
        ("certs/client.pem", "secret_filename"),
        (".venv/lib.py", "cache_or_environment"),
        (".git/config", "control_directory"),
    ],
)
def test_mandatory_exclusions(path: str, reason: str) -> None:
    assert exclusion_reason(path) == reason


def test_inline_secrets_are_redacted_and_bounded() -> None:
    source = "api_key = 'abcdefghijklmnopqrstuvwxyz123456'\nsk-abcdefghijklmnopqrstuvwxyz"
    redacted = redact_text(source, max_chars=100)
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "[REDACTED]" in redacted


def test_resolved_containment_accepts_inside_and_rejects_outside(tmp_path: Path) -> None:
    inside = tmp_path / "inside.py"
    inside.write_text("x = 1\n", encoding="utf-8")
    assert ensure_contained(tmp_path, inside) == inside.resolve()
    outside = tmp_path.parent / "outside.py"
    outside.write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(WeaverError):
        ensure_contained(tmp_path, outside)
