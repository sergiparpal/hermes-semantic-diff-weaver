from __future__ import annotations

import pytest

from hermes_semantic_diff_weaver.ast_diff import StructuralDelta
from hermes_semantic_diff_weaver.models import BehaviorCategory, LineRange
from hermes_semantic_diff_weaver.semantic_candidates import build_candidates


def delta(kind: str, old: str | None, new: str | None) -> StructuralDelta:
    return StructuralDelta(
        path="src/policy.py",
        symbol="Policy.apply",
        kind=kind,
        old=old,
        new=new,
        old_lines=LineRange(start=1, end=3),
        new_lines=LineRange(start=1, end=3),
        hunk_id="src/policy.py#hunk-001",
    )


@pytest.mark.parametrize(
    ("change", "category"),
    [
        (delta("comparison_change", "x < 5", "x <= 5"), BehaviorCategory.BOUNDARY),
        (
            StructuralDelta(
                **{
                    **delta("signature_change", "limit=2", "limit=3").__dict__,
                    "metadata": {"default_changed": True},
                }
            ),
            BehaviorCategory.DEFAULT_BEHAVIOR,
        ),
        (delta("raise_change", "ValueError", "TypeError"), BehaviorCategory.ERROR_HANDLING),
        (delta("condition_change", "is_valid(x)", "validate(x)"), BehaviorCategory.VALIDATION),
        (
            delta("condition_change", "user.is_owner", "user.is_admin"),
            BehaviorCategory.AUTHORIZATION,
        ),
        (delta("loop_change", "range(2)", "range(3)"), BehaviorCategory.RETRY_TIMEOUT),
        (delta("return_change", "{'old': 1}", "{'new': 1}"), BehaviorCategory.OUTPUT_CONTRACT),
        (
            delta("assignment_change", "state = old", "state = new"),
            BehaviorCategory.STATE_TRANSITION,
        ),
        (delta("call_change", None, "notify(user)"), BehaviorCategory.SIDE_EFFECT),
        (delta("call_order_change", "first; second", "second; first"), BehaviorCategory.ORDERING),
        (
            delta("call_change", "client.old()", "client.new()"),
            BehaviorCategory.DEPENDENCY_INTERACTION,
        ),
        (delta("structural_refactor", "old_name", "new_name"), BehaviorCategory.REFACTOR),
        (delta("unknown_structure", "body", "body"), BehaviorCategory.UNKNOWN),
    ],
)
def test_complete_taxonomy_rules(change: StructuralDelta, category: BehaviorCategory) -> None:
    candidates = build_candidates([change])
    assert candidates[0].category is category
    assert candidates[0].evidence[0].id == "ev-001"


def test_same_symbol_category_merges_evidence() -> None:
    candidates = build_candidates(
        [
            delta("comparison_change", "x < 1", "x <= 1"),
            delta("condition_change", "x < 1", "x <= 1"),
        ]
    )
    assert len(candidates) == 1
    assert [item.id for item in candidates[0].evidence] == ["ev-001", "ev-002"]
