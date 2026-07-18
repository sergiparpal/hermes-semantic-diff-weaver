from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hermes_semantic_diff_weaver.ast_diff import StructuralDelta
from hermes_semantic_diff_weaver.models import LineRange, WeaverConfig
from hermes_semantic_diff_weaver.semantic_candidates import build_candidates
from hermes_semantic_diff_weaver.semantic_interpreter import interpret_candidates


@dataclass
class Result:
    content_type: str
    parsed: Any
    usage: Any = None


class FakeLlm:
    def __init__(self, results: list[Result]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def complete_structured(self, **kwargs: Any) -> Result:
        self.calls.append(kwargs)
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


def candidate():
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


def valid_payload() -> dict[str, Any]:
    return {
        "behaviors": [
            {
                "category": "boundary_change",
                "summary": "The exact limit is now accepted.",
                "observable_impact": "A value of five may now be accepted.",
                "evidence_ids": ["ev-001"],
                "assumptions": [],
                "confidence": 0.9,
            }
        ],
        "obligations": [
            {
                "behavior_index": 0,
                "type": "boundary",
                "title": "Exercise five",
                "given": "A value of five",
                "when": "The check runs",
                "then": "The value is accepted",
            }
        ],
    }


def test_call_shape_uses_active_host_model_without_overrides() -> None:
    llm = FakeLlm(
        [
            Result(
                "json",
                valid_payload(),
                usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001},
            )
        ]
    )
    result = interpret_candidates([candidate()], llm, WeaverConfig())
    assert result.status.calls == 1
    assert result.status.available is True
    assert result.status.usage.input_tokens == 10
    call = llm.calls[0]
    assert not {"provider", "model", "agent_id", "profile"} & call.keys()
    assert call["schema_name"] == "semantic_diff_batch_v1"
    assert call["purpose"] == "semantic-diff-interpretation"
    assert "UNTRUSTED_SEMANTIC_DIFF_EVIDENCE" in call["input"][0]["text"]
    assert result.suggestions


def test_text_result_retries_once_then_falls_back() -> None:
    llm = FakeLlm([Result("text", None)])
    result = interpret_candidates([candidate()], llm, WeaverConfig())
    assert len(llm.calls) == 2
    assert result.status.available is False
    assert result.status.failures == 1
    assert result.candidates
    assert result.warnings


def test_call_count_never_exceeds_eight() -> None:
    candidates = []
    for index in range(20):
        item = candidate()
        item.evidence[0].id = f"ev-{index + 1:03d}"
        item.evidence[0].path = f"src/module_{index}.py"
        candidates.append(item)
    llm = FakeLlm([Result("json", {"behaviors": [], "obligations": []})])
    config = WeaverConfig()
    result = interpret_candidates(candidates, llm, config)
    assert result.status.calls <= 8
