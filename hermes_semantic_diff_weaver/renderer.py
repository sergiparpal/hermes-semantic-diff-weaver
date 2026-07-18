"""Deterministic canonical JSON transport and concise Markdown rendering."""

from __future__ import annotations

import re
from typing import Any

from .models import AnalysisResult, BothEnvelope, MarkdownEnvelope, OutputFormat


def _escape(text: str) -> str:
    controlled = text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", controlled)


def _fenced_summary(label: str, text: str) -> list[str]:
    safe = text.replace("`", "'").replace("\r", "\\r").replace("\t", "\\t")
    return [f"    {label}: {line}" for line in safe.splitlines() or [""]]


def render_markdown(result: AnalysisResult) -> str:
    lines = [
        "## Semantic Diff Test Brief",
        "",
        (
            f"**Overall risk:** {result.summary.overall_risk.value} "
            f"({result.summary.risk_score}/100) · **Confidence:** "
            f"{result.summary.overall_confidence:.0%}"
        ),
        (
            f"**Scope:** {len(result.scope.analyzed_files)}/{result.scope.changed_files_total} "
            "changed file(s) analyzed, "
            f"{result.summary.changed_symbols} changed symbol(s), "
            f"{sum(item.count for item in result.scope.omitted)} omitted item(s), "
            f"{sum(result.scope.excluded_counts.values())} excluded file(s)"
            f"{' (truncated)' if result.scope.truncated else ''}."
        ),
        "",
        "### Inferred behavior changes",
        "",
    ]
    if not result.behavior_changes:
        lines.append(
            "No reportable Python behavior change was inferred from the bounded static evidence."
        )
    for behavior in result.behavior_changes:
        prefix = (
            "Review question" if behavior.presentation.value == "review_question" else "Finding"
        )
        lines.extend(
            [
                f"- **{prefix} · {_escape(behavior.category.value)} · {behavior.risk.value} "
                f"risk · {behavior.confidence:.0%} confidence:** {_escape(behavior.summary)}",
                f"  - Observable impact: {_escape(behavior.observable_impact)}",
            ]
        )
        for evidence in behavior.evidence:
            location = _escape(evidence.path)
            if evidence.symbol:
                location += f" — `{_escape(evidence.symbol)}`"
            ranges = []
            if evidence.old_lines:
                ranges.append(f"old {evidence.old_lines.start}-{evidence.old_lines.end}")
            if evidence.new_lines:
                ranges.append(f"new {evidence.new_lines.start}-{evidence.new_lines.end}")
            suffix = f" ({', '.join(ranges)})" if ranges else ""
            lines.append(f"  - Evidence `{evidence.id}`: {location}{suffix}")
            if evidence.old or evidence.new:
                lines.extend(["    ````text", *_fenced_summary("old", evidence.old or "∅")])
                lines.extend([*_fenced_summary("new", evidence.new or "∅"), "    ````"])
    lines.extend(["", "### Prioritized test obligations", ""])
    if not result.test_obligations:
        lines.append("No test obligations were generated.")
    for obligation in result.test_obligations:
        lines.extend(
            [
                f"- [ ] **P{obligation.priority} — {_escape(obligation.title)}**",
                f"  - Given: {_escape(obligation.given)}",
                f"  - When: {_escape(obligation.when)}",
                f"  - Then: {_escape(obligation.then)}",
            ]
        )
        if obligation.candidate_existing_tests:
            candidates = ", ".join(
                f"`{_escape(item.path)}::{_escape(item.symbol)}` ({item.match_score:.2f}; "
                f"{_escape(', '.join(item.match_reasons))})"
                for item in obligation.candidate_existing_tests
            )
            lines.append(f"  - Candidate existing tests (unverified): {candidates}")
        else:
            lines.append(f"  - Candidate existing tests: none ({obligation.coverage_status.value})")
    review = [
        item for item in result.behavior_changes if item.presentation.value == "review_question"
    ]
    if review:
        lines.extend(["", "### Review questions", ""])
        lines.extend(f"- {_escape(item.observable_impact)}" for item in review)
    if result.warnings:
        lines.extend(["", "### Warnings", ""])
        lines.extend(f"- {_escape(item)}" for item in result.warnings)
    if result.limitations:
        lines.extend(["", "### Limitations", ""])
        lines.extend(f"- {_escape(item)}" for item in result.limitations)
    lines.extend(
        [
            "",
            "_Advisory static analysis only: no tests or repository code were executed, and candidate "
            "test mappings do not verify runtime coverage._",
        ]
    )
    return "\n".join(lines)


def render_transport(result: AnalysisResult, output_format: OutputFormat) -> dict[str, Any]:
    if output_format is OutputFormat.JSON:
        return result.model_dump(mode="json")
    markdown = render_markdown(result)
    if output_format is OutputFormat.MARKDOWN:
        return MarkdownEnvelope(analysis_id=result.analysis_id, markdown=markdown).model_dump(
            mode="json"
        )
    return BothEnvelope(analysis=result, markdown=markdown).model_dump(mode="json")
