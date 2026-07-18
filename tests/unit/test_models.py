from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes_semantic_diff_weaver.models import (
    AnalysisResult,
    AnalyzeRequest,
    BehaviorCategory,
    CandidateTest,
    ErrorResponse,
    LineRange,
    WeaverConfig,
)


def test_request_defaults_and_unknown_field() -> None:
    request = AnalyzeRequest(repo_path=".", base_ref="main")
    assert request.head_ref == "HEAD"
    assert request.output_format.value == "both"
    with pytest.raises(ValidationError):
        AnalyzeRequest(repo_path=".", base_ref="main", surprise=True)


def test_taxonomy_is_exact() -> None:
    assert len(BehaviorCategory) == 13
    assert BehaviorCategory("boundary_change") is BehaviorCategory.BOUNDARY
    with pytest.raises(ValueError):
        BehaviorCategory("business_rule_change")


def test_line_ranges_are_ordered() -> None:
    assert LineRange(start=2, end=3).end == 3
    with pytest.raises(ValidationError):
        LineRange(start=3, end=2)


def test_config_defaults_validate() -> None:
    config = WeaverConfig()
    assert config.rules.max_llm_calls == 8
    assert config.privacy.allow_network is False


def test_candidate_tests_are_explicitly_unverified() -> None:
    candidate = CandidateTest(
        path="tests/test_api.py",
        symbol="test_api",
        match_score=0.5,
        match_reasons=["direct module or symbol import"],
    )
    assert candidate.verified is False
    with pytest.raises(ValidationError):
        CandidateTest(
            path="tests/test_api.py",
            symbol="test_api",
            match_score=0.5,
            match_reasons=["name"],
            verified=True,
        )


def test_transport_schemas_are_versioned() -> None:
    assert AnalysisResult.model_json_schema()["properties"]["schema_version"]["const"] == "1.0"
    assert ErrorResponse(success=False, error="invalid_ref", message="bad", remediation="fix")
