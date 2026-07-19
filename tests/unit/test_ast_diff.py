from __future__ import annotations

from hermes_semantic_diff_weaver.ast_diff import analyze_ast
from hermes_semantic_diff_weaver.git_diff import ChangedFile, Hunk


def changed(old: str, new: str) -> ChangedFile:
    return ChangedFile(
        status="M",
        old_path="src/sample.py",
        new_path="src/sample.py",
        hunks=[Hunk(id="hunk-001", old_start=1, old_count=100, new_start=1, new_count=100)],
        old_text=old,
        new_text=new,
    )


def kinds(old: str, new: str) -> set[str]:
    return {item.kind for item in analyze_ast([changed(old, new)]).deltas}


def test_extracts_required_structural_delta_classes() -> None:
    assert "comparison_change" in kinds(
        "def allowed(x):\n    return x < 5\n", "def allowed(x):\n    return x <= 5\n"
    )
    assert "signature_change" in kinds(
        "def run(limit=2):\n    return limit\n", "def run(limit=3):\n    return limit\n"
    )
    assert "signature_change" in kinds(
        "def run(value: int) -> int:\n    return value\n",
        "def run(value: int) -> str:\n    return value\n",
    )
    assert "raise_change" in kinds(
        "def run():\n    raise ValueError()\n", "def run():\n    raise TypeError()\n"
    )
    assert "return_change" in kinds(
        "def run():\n    return {'old': 1}\n", "def run():\n    return {'new': 1}\n"
    )
    assert "assignment_change" in kinds(
        "def run(x):\n    state = x\n    return state\n",
        "def run(x):\n    state = x + 1\n    return state\n",
    )
    assert "loop_change" in kinds(
        "def run():\n    for x in range(2):\n        pass\n",
        "def run():\n    for x in range(3):\n        pass\n",
    )


def test_unchanged_symbol_outside_hunk_is_ignored() -> None:
    file = ChangedFile(
        status="M",
        old_path="src/sample.py",
        new_path="src/sample.py",
        hunks=[Hunk(id="hunk-001", old_start=5, old_count=1, new_start=5, new_count=1)],
        old_text="def unchanged(x):\n    return x < 5\n\nvalue = 1\n",
        new_text="def unchanged(x):\n    return x < 5\n\nvalue = 2\n",
    )
    analysis = analyze_ast([file])
    assert all(item.symbol != "unchanged" for item in analysis.deltas)


def test_partial_parse_failure_preserves_other_file() -> None:
    good = changed("def f(x):\n    return x < 2\n", "def f(x):\n    return x <= 2\n")
    bad = ChangedFile(
        status="M",
        old_path="src/bad.py",
        new_path="src/bad.py",
        hunks=[Hunk(id="hunk-001", old_start=1, old_count=1, new_start=1, new_count=1)],
        old_text="def broken(:\n",
        new_text="def still_broken(:\n",
    )
    analysis = analyze_ast([good, bad])
    assert analysis.parsed_files == 1
    assert analysis.failed_files == 1
    assert analysis.deltas
    assert analysis.warnings
