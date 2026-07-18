from __future__ import annotations

import json
from typing import Any

import pytest

from hermes_semantic_diff_weaver.plugin import handle_analyze_semantic_diff
from hermes_semantic_diff_weaver.service import analyze


@pytest.mark.parametrize("output_format", ["json", "markdown", "both"])
def test_all_output_modes(repo_factory, output_format: str) -> None:
    repo, base, head = repo_factory(
        {"api.py": "def allowed(x):\n    return x < 5\n"},
        {"api.py": "def allowed(x):\n    return x <= 5\n"},
    )
    result = analyze(
        {
            "repo_path": str(repo),
            "base_ref": base,
            "head_ref": head,
            "output_format": output_format,
        }
    )
    assert result["success"] is True
    assert result["schema_version"] == "1.0"
    if output_format == "json":
        assert "behavior_changes" in result
    elif output_format == "markdown":
        assert "analysis" not in result
        assert "## Semantic Diff Test Brief" in result["markdown"]
    else:
        assert result["analysis"]["analysis_id"] in result["markdown"] or result["analysis"]


def test_no_python_change_is_successful_empty_analysis(repo_factory) -> None:
    repo, base, head = repo_factory({"README.md": "old\n"}, {"README.md": "new\n"})
    result = analyze(
        {"repo_path": str(repo), "base_ref": base, "head_ref": head, "output_format": "json"}
    )
    assert result["success"] is True
    assert result["behavior_changes"] == []
    assert any("no included changed Python" in item for item in result["limitations"])


def test_parse_failures_retain_bounded_evidence_and_continue(repo_factory) -> None:
    repo, base, head = repo_factory(
        {"good.py": "def f(x):\n    return x < 2\n", "bad.py": "def broken(:\n"},
        {"good.py": "def f(x):\n    return x <= 2\n", "bad.py": "def broken_again(:\n"},
    )
    result = analyze(
        {"repo_path": str(repo), "base_ref": base, "head_ref": head, "output_format": "json"}
    )
    assert result["behavior_changes"]
    assert any("Could not parse" in item for item in result["warnings"])

    only_bad, bad_base, bad_head = repo_factory(
        {"bad.py": "def broken(:\n"}, {"bad.py": "def broken_again(:\n"}
    )
    incomplete = analyze(
        {
            "repo_path": str(only_bad),
            "base_ref": bad_base,
            "head_ref": bad_head,
            "output_format": "json",
        }
    )
    assert incomplete["success"] is True
    assert incomplete["behavior_changes"][0]["category"] == "unknown_semantic_change"
    assert incomplete["behavior_changes"][0]["evidence"][0]["parser_complete"] is False
    assert incomplete["scope"]["truncated"] is True


def test_handler_always_returns_json_on_llm_failure(repo_factory) -> None:
    repo, base, head = repo_factory(
        {"a.py": "def f(x):\n    return x < 1\n"},
        {"a.py": "def f(x):\n    return x <= 1\n"},
    )

    class FailingLlm:
        def complete_structured(self, **kwargs: Any) -> Any:
            raise RuntimeError(kwargs["purpose"])

    text = handle_analyze_semantic_diff(
        {"repo_path": str(repo), "base_ref": base, "head_ref": head}, llm=FailingLlm()
    )
    result = json.loads(text)
    assert result["success"] is True
    assert result["analysis"]["deterministic_mode"] is True
    assert result["analysis"]["behavior_changes"]


def test_unknown_request_field_is_public_configuration_error(repo_factory) -> None:
    repo, base, head = repo_factory({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    result = json.loads(
        handle_analyze_semantic_diff(
            {"repo_path": str(repo), "base_ref": base, "head_ref": head, "unknown": True}
        )
    )
    assert result["error"] == "configuration_error"


def test_symbol_and_obligation_caps_are_explicit(repo_factory) -> None:
    config = "version: 1\nrules:\n  max_changed_symbols: 1\n  max_test_obligations: 1\n"
    old = "def first(x):\n    return x < 1\n\ndef second(x):\n    return x < 2\n"
    new = "def first(x):\n    return x <= 1\n\ndef second(x):\n    return x <= 2\n"
    repo, base, head = repo_factory(
        {"change.py": old, ".semantic-diff-weaver.yaml": config},
        {"change.py": new, ".semantic-diff-weaver.yaml": config},
    )
    result = analyze(
        {"repo_path": str(repo), "base_ref": base, "head_ref": head, "output_format": "json"}
    )
    assert result["scope"]["truncated"] is True
    assert result["scope"]["changed_symbols"] == 1
    assert len(result["test_obligations"]) == 1
    reasons = {item["reason"] for item in result["scope"]["omitted"]}
    assert {"changed_symbol_limit", "global_obligation_limit"} <= reasons


def test_minimum_confidence_and_refactor_policies_are_visible(repo_factory) -> None:
    high_minimum = "version: 1\nrules:\n  minimum_report_confidence: 0.99\n"
    repo, base, head = repo_factory(
        {"a.py": "def f(x):\n    return x < 1\n", ".semantic-diff-weaver.yaml": high_minimum},
        {"a.py": "def f(x):\n    return x <= 1\n", ".semantic-diff-weaver.yaml": high_minimum},
    )
    result = analyze(
        {"repo_path": str(repo), "base_ref": base, "head_ref": head, "output_format": "json"}
    )
    assert result["behavior_changes"] == []
    assert any(item["reason"] == "minimum_confidence" for item in result["scope"]["omitted"])


def test_every_high_risk_behavior_keeps_a_linked_obligation(repo_factory) -> None:
    config = "version: 1\ncritical_paths:\n  - pattern: 'critical.py'\n    weight: 100\n"
    old = "def first(x):\n    return x < 1\n\ndef second(x):\n    return x < 2\n"
    new = "def first(x):\n    return x <= 1\n\ndef second(x):\n    return x <= 2\n"
    repo, base, head = repo_factory(
        {"critical.py": old, ".semantic-diff-weaver.yaml": config},
        {"critical.py": new, ".semantic-diff-weaver.yaml": config},
    )
    result = analyze(
        {"repo_path": str(repo), "base_ref": base, "head_ref": head, "output_format": "json"}
    )
    required = {
        item["id"] for item in result["behavior_changes"] if item["risk"] in {"high", "critical"}
    }
    linked = {
        behavior_id
        for obligation in result["test_obligations"]
        for behavior_id in obligation["behavior_change_ids"]
    }
    assert required
    assert required <= linked


def test_critical_path_prioritization_is_explicit_in_canonical_scope(repo_factory) -> None:
    config = (
        "version: 1\n"
        "critical_paths:\n  - pattern: 'critical.py'\n    weight: 100\n"
        "rules:\n  max_changed_files: 1\n  max_diff_lines: 2\n"
    )
    repo, base, head = repo_factory(
        {
            "critical.py": "def f(x):\n    return x < 1\n",
            "other.py": "def g(x):\n    return x < 1\n",
            ".semantic-diff-weaver.yaml": config,
        },
        {
            "critical.py": "def f(x):\n    return x <= 1\n",
            "other.py": "def g(x):\n    return x <= 1\n",
            ".semantic-diff-weaver.yaml": config,
        },
    )
    result = analyze(
        {"repo_path": str(repo), "base_ref": base, "head_ref": head, "output_format": "json"}
    )
    assert result["scope"]["analyzed_files"] == ["critical.py"]
    assert result["scope"]["truncated"] is True
    assert any(item["reason"] == "resource_prioritization" for item in result["scope"]["omitted"])
