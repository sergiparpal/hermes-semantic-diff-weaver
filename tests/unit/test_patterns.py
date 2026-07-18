from __future__ import annotations

from hermes_semantic_diff_weaver.ast_diff import StructuralDelta
from hermes_semantic_diff_weaver.models import BehaviorCategory, LineRange
from hermes_semantic_diff_weaver.semantic_candidates import build_candidates


def candidate(kind: str, old: str, new: str):
    change = StructuralDelta(
        path="src/change.py",
        symbol="change",
        kind=kind,
        old=old,
        new=new,
        old_lines=LineRange(start=1, end=1),
        new_lines=LineRange(start=1, end=1),
        hunk_id="src/change.py#hunk-001",
    )
    return build_candidates([change])[0]


def test_name_hints_carry_assumptions_and_capped_confidence() -> None:
    result = candidate("condition_change", "user.is_owner", "user.is_admin")
    assert result.category is BehaviorCategory.AUTHORIZATION
    assert result.confidence_baseline <= 0.75
    assert result.assumptions


def test_material_unknown_stays_explicit() -> None:
    result = candidate("unknown_structure", "old bytecode factory", "new bytecode factory")
    assert result.category is BehaviorCategory.UNKNOWN
    assert "review" in result.observable_impact
