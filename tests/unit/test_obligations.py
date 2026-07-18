from __future__ import annotations

from hermes_semantic_diff_weaver.models import (
    BehaviorCategory,
    BehaviorChange,
    Evidence,
    Origin,
    Presentation,
    RiskLabel,
    ScoreExplanation,
    WeaverConfig,
)
from hermes_semantic_diff_weaver.obligations import generate_obligations


def behavior(category: BehaviorCategory, index: int = 1, risk: RiskLabel = RiskLabel.HIGH):
    return BehaviorChange(
        id=f"bc-{index:03d}",
        category=category,
        summary="Changed behavior.",
        observable_impact="An outcome appears to differ.",
        risk=risk,
        risk_score=70 if risk is RiskLabel.HIGH else 20,
        confidence=0.8,
        evidence=[Evidence(id=f"ev-{index:03d}", path="src/a.py", kind="comparison_change")],
        assumptions=[],
        presentation=Presentation.FINDING,
        origin=Origin.DETERMINISTIC,
        score_explanation=ScoreExplanation(
            behavioral_impact=70,
            critical_path_weight=10,
            test_gap_weight=90,
            change_surface_weight=30,
        ),
    )


def test_boundary_generates_below_at_above_obligations() -> None:
    obligations, omitted = generate_obligations(
        [behavior(BehaviorCategory.BOUNDARY)], {}, False, WeaverConfig()
    )
    assert omitted == 0
    assert len(obligations) == 3
    assert any("below" in item.title for item in obligations)
    assert any("exact" in item.title for item in obligations)
    assert any("above" in item.title for item in obligations)
    assert all(item.behavior_change_ids == ["bc-001"] for item in obligations)


def test_high_behavior_always_has_obligation_and_cap_is_visible() -> None:
    config = WeaverConfig()
    config.rules.max_test_obligations = 2
    obligations, omitted = generate_obligations(
        [behavior(BehaviorCategory.RETRY_TIMEOUT)], {}, False, config
    )
    assert obligations
    assert len(obligations) == 2
    assert omitted == 1


def test_mapping_incomplete_is_not_claimed_as_coverage() -> None:
    obligations, _ = generate_obligations(
        [behavior(BehaviorCategory.ERROR_HANDLING)], {}, True, WeaverConfig()
    )
    assert all(item.coverage_status.value == "mapping_incomplete" for item in obligations)


def test_equivalent_templates_do_not_remove_another_high_risk_behaviors_obligation() -> None:
    obligations, _ = generate_obligations(
        [
            behavior(BehaviorCategory.BOUNDARY, index=1),
            behavior(BehaviorCategory.BOUNDARY, index=2),
        ],
        {},
        False,
        WeaverConfig(),
    )
    linked = {
        behavior_id for obligation in obligations for behavior_id in obligation.behavior_change_ids
    }
    assert {"bc-001", "bc-002"} <= linked


def test_global_cap_groups_overflowing_high_risk_behavior_links() -> None:
    config = WeaverConfig()
    config.rules.max_test_obligations = 2
    obligations, omitted = generate_obligations(
        [behavior(BehaviorCategory.BOUNDARY, index=index) for index in range(1, 4)],
        {},
        False,
        config,
    )
    linked = {
        behavior_id for obligation in obligations for behavior_id in obligation.behavior_change_ids
    }
    assert len(obligations) == 2
    assert omitted == 7
    assert linked == {"bc-001", "bc-002", "bc-003"}
