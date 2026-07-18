from __future__ import annotations

from hermes_semantic_diff_weaver.ast_diff import analyze_ast
from hermes_semantic_diff_weaver.git_diff import ChangedFile, Hunk


def file(old: str, new: str) -> ChangedFile:
    return ChangedFile(
        status="M",
        old_path="src/a.py",
        new_path="src/a.py",
        old_text=old,
        new_text=new,
        hunks=[Hunk(id="hunk-001", old_start=1, old_count=20, new_start=1, new_count=20)],
    )


def test_conservative_rename_uses_fingerprint_and_signature() -> None:
    result = analyze_ast(
        [file("def old_name(x):\n    return x + 1\n", "def new_name(x):\n    return x + 1\n")]
    )
    assert any(item.kind == "structural_refactor" for item in result.deltas)
    assert not any(item.kind in {"symbol_added", "symbol_removed"} for item in result.deltas)


def test_ambiguous_rename_is_not_forced() -> None:
    result = analyze_ast(
        [
            file(
                "def old(x):\n    return x + 1\n",
                "def first(x):\n    return x + 1\n\ndef second(x):\n    return x + 1\n",
            )
        ]
    )
    assert result.warnings
    assert any(item.kind == "symbol_removed" for item in result.deltas)
    assert sum(item.kind == "symbol_added" for item in result.deltas) == 2


def test_conservative_similarity_matches_a_rename_with_a_small_body_change() -> None:
    result = analyze_ast(
        [file("def old_name(x):\n    return x + 1\n", "def new_name(x):\n    return x + 2\n")]
    )
    assert any(item.kind == "return_change" for item in result.deltas)
    assert not any(item.kind in {"symbol_added", "symbol_removed"} for item in result.deltas)
