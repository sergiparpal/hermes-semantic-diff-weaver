from __future__ import annotations

import hermes_semantic_diff_weaver.test_mapper as test_mapper
from hermes_semantic_diff_weaver.ast_diff import StructuralDelta
from hermes_semantic_diff_weaver.models import LineRange, WeaverConfig
from hermes_semantic_diff_weaver.semantic_candidates import build_candidates
from hermes_semantic_diff_weaver.test_mapper import (
    IndexedTest,
    TestIndex,
    build_test_index,
    map_candidate_tests,
)


def boundary_candidate():
    return build_candidates(
        [
            StructuralDelta(
                path="src/api.py",
                symbol="allowed",
                kind="comparison_change",
                old="x < 5",
                new="x <= 5",
                old_lines=LineRange(start=2, end=2),
                new_lines=LineRange(start=2, end=2),
                hunk_id="src/api.py#hunk-001",
            )
        ]
    )[0]


def test_terminology_alone_cannot_create_candidate() -> None:
    index = TestIndex(
        tests=[
            IndexedTest(
                path="tests/test_other.py",
                symbol="test_boundary",
                imports=frozenset(),
                name_tokens=frozenset({"test", "boundary"}),
                body_tokens=frozenset({"threshold"}),
            )
        ],
        incomplete=False,
        warnings=[],
    )
    assert map_candidate_tests([boundary_candidate()], index, WeaverConfig())[0] == []


def test_structural_features_rank_and_cap_stably() -> None:
    tests = [
        IndexedTest(
            path=f"tests/test_api_{index}.py",
            symbol=f"test_allowed_{index}",
            imports=frozenset({"src.api"}),
            name_tokens=frozenset({"test", "allowed", str(index)}),
            body_tokens=frozenset({"allowed", "boundary"}),
        )
        for index in range(8)
    ]
    mapped = map_candidate_tests(
        [boundary_candidate()],
        TestIndex(tests=tests, incomplete=False, warnings=[]),
        WeaverConfig(),
    )[0]
    assert len(mapped) == 5
    assert all(item.verified is False for item in mapped)
    assert mapped == sorted(mapped, key=lambda item: (-item.match_score, item.path, item.symbol))


def test_test_index_has_aggregate_file_and_byte_caps(monkeypatch) -> None:
    class FakeRepository:
        def list_files(self, commit: str) -> list[str]:
            return ["tests/test_a.py", "tests/test_b.py"]

        def read_blob(self, commit: str, path: str, max_bytes: int) -> str:
            return "def test_value():\n    assert True\n"

    monkeypatch.setattr(test_mapper, "MAX_TEST_INDEX_FILES", 1)
    index = build_test_index(FakeRepository(), "a" * 40, WeaverConfig())
    assert index.incomplete is True
    assert len(index.tests) == 1
    assert any("capped" in warning for warning in index.warnings)

    monkeypatch.setattr(test_mapper, "MAX_TEST_INDEX_FILES", 500)
    monkeypatch.setattr(test_mapper, "MAX_TEST_INDEX_BYTES", 1)
    byte_limited = build_test_index(FakeRepository(), "a" * 40, WeaverConfig())
    assert byte_limited.incomplete is True
    assert byte_limited.tests == []
    assert any("byte cap" in warning for warning in byte_limited.warnings)
