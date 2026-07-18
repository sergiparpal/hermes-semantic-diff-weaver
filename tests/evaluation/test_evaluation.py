from __future__ import annotations

import json
from pathlib import Path

from hermes_semantic_diff_weaver.ast_diff import analyze_ast
from hermes_semantic_diff_weaver.git_diff import ChangedFile, Hunk
from hermes_semantic_diff_weaver.semantic_candidates import build_candidates


def test_supported_pattern_precision_recall_and_evidence_gates() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "evaluation_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    true_positive = 0
    predicted_total = 0
    expected_total = 0
    fabricated = 0
    for case in cases:
        changed = ChangedFile(
            status="M",
            old_path="src/case.py",
            new_path="src/case.py",
            old_text=case["old"],
            new_text=case["new"],
            hunks=[Hunk(id="hunk-001", old_start=1, old_count=100, new_start=1, new_count=100)],
        )
        candidates = build_candidates(analyze_ast([changed]).deltas)
        predicted = {item.category.value for item in candidates}
        expected = set(case["expected"])
        true_positive += len(predicted & expected)
        predicted_total += len(predicted)
        expected_total += len(expected)
        evidence_ids = {evidence.id for item in candidates for evidence in item.evidence}
        fabricated += sum(not evidence_id.startswith("ev-") for evidence_id in evidence_ids)
        assert all(item.evidence for item in candidates)
    precision = true_positive / predicted_total
    recall = true_positive / expected_total
    assert precision >= 0.80
    assert recall >= 0.70
    assert fabricated == 0
