from __future__ import annotations

import time

import pytest

from hermes_semantic_diff_weaver.ast_diff import analyze_ast
from hermes_semantic_diff_weaver.git_diff import ChangedFile, Hunk


@pytest.mark.performance
def test_near_symbol_limit_preprocessing_is_under_reference_target() -> None:
    old = "\n\n".join(f"def function_{index}(x):\n    return x < {index}" for index in range(100))
    new = "\n\n".join(f"def function_{index}(x):\n    return x <= {index}" for index in range(100))
    changed = ChangedFile(
        status="M",
        old_path="src/generated_fixture.py",
        new_path="src/generated_fixture.py",
        old_text=old,
        new_text=new,
        hunks=[Hunk(id="hunk-001", old_start=1, old_count=1000, new_start=1, new_count=1000)],
    )
    started = time.perf_counter()
    result = analyze_ast([changed])
    elapsed = time.perf_counter() - started
    assert result.changed_symbols == 100
    assert elapsed < 5.0
