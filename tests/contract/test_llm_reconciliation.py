from __future__ import annotations

from hermes_semantic_diff_weaver.models import BehaviorCategory, WeaverConfig
from hermes_semantic_diff_weaver.semantic_interpreter import interpret_candidates
from tests.contract.test_llm_call import FakeLlm, Result, candidate, valid_payload


def test_fabricated_evidence_is_discarded() -> None:
    payload = valid_payload()
    payload["behaviors"][0]["evidence_ids"] = ["ev-999"]
    result = interpret_candidates([candidate()], FakeLlm([Result("json", payload)]), WeaverConfig())
    assert len(result.candidates) == 1
    assert any("fabricated evidence" in item for item in result.warnings)


def test_unsupported_category_is_downgraded() -> None:
    payload = valid_payload()
    payload["behaviors"][0]["category"] = "authorization_change"
    result = interpret_candidates([candidate()], FakeLlm([Result("json", payload)]), WeaverConfig())
    assert any(item.category is BehaviorCategory.UNKNOWN for item in result.candidates)
    assert any("Downgraded" in item for item in result.warnings)


def test_unknown_taxonomy_fails_local_validation_and_preserves_deterministic() -> None:
    payload = valid_payload()
    payload["behaviors"][0]["category"] = "invented_change"
    result = interpret_candidates([candidate()], FakeLlm([Result("json", payload)]), WeaverConfig())
    assert len(result.candidates) == 1
    assert result.status.failures == 1
    assert result.candidates[0].category is BehaviorCategory.BOUNDARY
