"""Typed orchestration for the bounded read-only semantic diff pipeline."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from .ast_diff import StructuralDelta, analyze_ast
from .config import load_config
from .errors import ErrorCode, WeaverError
from .git_diff import GitRepository, collect_diff
from .models import (
    AnalysisResult,
    AnalyzeRequest,
    BehaviorChange,
    LlmStatus,
    OmittedScope,
    Origin,
    Presentation,
    RepositoryIdentity,
    RiskLabel,
    ScopeMetadata,
    Summary,
    WeaverConfig,
)
from .obligations import generate_obligations
from .path_policy import glob_matches, redact_text
from .renderer import render_transport
from .scoring import confidence_score, score_risk
from .semantic_candidates import SemanticCandidate, build_candidates
from .semantic_interpreter import interpret_candidates
from .test_mapper import build_test_index, map_candidate_tests


def _validation_error(exc: ValidationError) -> WeaverError:
    location = ".".join(str(item) for item in exc.errors()[0].get("loc", ())) or "request"
    return WeaverError(
        ErrorCode.CONFIGURATION_ERROR,
        f"Invalid tool argument at {location}.",
        "Check required fields, output_format, include/exclude patterns, and unknown fields.",
    )


def _prioritize_deltas(
    deltas: list[StructuralDelta], maximum: int, config: WeaverConfig
) -> tuple[list[StructuralDelta], int]:
    grouped: dict[tuple[str, str], list[StructuralDelta]] = defaultdict(list)
    for delta in deltas:
        grouped[(delta.path, delta.symbol)].append(delta)
    ordered = sorted(
        grouped.items(),
        key=lambda item: (
            -max(
                (
                    critical.weight
                    for critical in config.critical_paths
                    if glob_matches(item[0][0], critical.pattern)
                ),
                default=0,
            ),
            -sum(
                delta.kind
                in {
                    "signature_change",
                    "comparison_change",
                    "raise_change",
                    "call_change",
                }
                for delta in item[1]
            ),
            item[0],
        ),
    )
    selected = ordered[:maximum]
    return [delta for _, items in selected for delta in items], max(0, len(ordered) - maximum)


def _read_readme_excerpt(repo: GitRepository, head_commit: str, config: WeaverConfig) -> str | None:
    if config.rules.max_readme_chars == 0:
        return None
    readme = next(
        (
            path
            for path in repo.list_files(head_commit)
            if path.rsplit("/", 1)[-1].casefold()
            in {"readme", "readme.md", "readme.rst", "readme.txt"}
        ),
        None,
    )
    if readme is None:
        return None
    source = repo.read_blob(
        head_commit,
        readme,
        min(config.rules.max_file_bytes, max(4096, config.rules.max_readme_chars * 4)),
    )
    if source is None:
        return None
    return redact_text(source, max_chars=config.rules.max_readme_chars)


def _deduplicate_candidates(candidates: list[SemanticCandidate]) -> list[SemanticCandidate]:
    output: list[SemanticCandidate] = []

    def normalized(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()

    for candidate in candidates:
        candidate_evidence = {item.id for item in candidate.evidence}
        existing = next(
            (
                item
                for item in output
                if item.path == candidate.path
                and item.symbol == candidate.symbol
                and item.category is candidate.category
                and (
                    candidate_evidence & {evidence.id for evidence in item.evidence}
                    or normalized(item.observable_impact) == normalized(candidate.observable_impact)
                )
            ),
            None,
        )
        if existing is None:
            output.append(candidate)
            continue
        if candidate.confidence_baseline > existing.confidence_baseline:
            existing.summary = candidate.summary
            existing.observable_impact = candidate.observable_impact
            existing.confidence_baseline = candidate.confidence_baseline
        evidence_by_id = {item.id: item for item in existing.evidence}
        for evidence in candidate.evidence:
            evidence_by_id.setdefault(evidence.id, evidence)
        existing.evidence = [evidence_by_id[key] for key in sorted(evidence_by_id)]
        existing.assumptions = sorted(set([*existing.assumptions, *candidate.assumptions]))
        existing.rule_ids = sorted(set([*existing.rule_ids, *candidate.rule_ids]))
        existing.related_calls.update(candidate.related_calls)
        existing.related_paths.update(candidate.related_paths)
        if candidate.origin is Origin.LLM_SUPPORTED:
            existing.origin = Origin.LLM_SUPPORTED
    return output


def analyze(arguments: dict[str, Any], *, llm: Any = None) -> dict[str, Any]:
    """Analyze committed Python changes and return the requested transport dictionary."""
    try:
        request = AnalyzeRequest.model_validate(arguments)
    except ValidationError as exc:
        raise _validation_error(exc) from exc
    repo = GitRepository.open(request.repo_path)
    base_commit = repo.resolve_ref(request.base_ref)
    head_commit = repo.resolve_ref(request.head_ref)
    config, config_warnings = load_config(repo.root, request)
    collection = collect_diff(repo, base_commit, head_commit, config)
    ast_result = analyze_ast(collection.files)
    omitted = [
        OmittedScope(reason=reason, count=count)
        for reason, count in sorted(collection.omitted_counts.items())
        if count
    ]
    scope_truncated = collection.truncated
    confidence_truncated = collection.truncated
    if ast_result.failed_files:
        omitted.append(OmittedScope(reason="parse_incomplete_files", count=ast_result.failed_files))
        scope_truncated = True
    deltas = ast_result.deltas
    changed_symbols = ast_result.changed_symbols
    if changed_symbols > config.rules.max_changed_symbols:
        deltas, omitted_count = _prioritize_deltas(deltas, config.rules.max_changed_symbols, config)
        omitted.append(OmittedScope(reason="changed_symbol_limit", count=omitted_count))
        changed_symbols = config.rules.max_changed_symbols
        scope_truncated = True
        confidence_truncated = True
    deterministic = build_candidates(deltas, config)
    interpreted = interpret_candidates(
        deterministic,
        llm,
        config,
        readme_excerpt=_read_readme_excerpt(repo, head_commit, config),
    )
    if interpreted.omitted_batches:
        omitted.append(OmittedScope(reason="llm_batch_limit", count=interpreted.omitted_batches))
        scope_truncated = True
        confidence_truncated = True
    if interpreted.truncated_evidence_symbols:
        omitted.append(
            OmittedScope(
                reason="model_evidence_limit",
                count=interpreted.truncated_evidence_symbols,
            )
        )
        scope_truncated = True
        confidence_truncated = True
    candidates = _deduplicate_candidates(interpreted.candidates)
    reportable: list[SemanticCandidate] = []
    confidence_by_index: dict[int, float] = {}
    warnings = [
        *config_warnings,
        *collection.warnings,
        *ast_result.warnings,
        *interpreted.warnings,
    ]
    low_confidence_omitted = 0
    refactors_omitted = 0
    for candidate in candidates:
        confidence = confidence_score(candidate, truncated=confidence_truncated)
        if (
            candidate.category.value == "refactor_likely_no_behavior_change"
            and not config.rules.emit_low_risk_refactors
        ):
            refactors_omitted += 1
            continue
        if confidence < config.rules.minimum_report_confidence:
            low_confidence_omitted += 1
            continue
        confidence_by_index[id(candidate)] = confidence
        reportable.append(candidate)
    if low_confidence_omitted:
        warnings.append(
            f"Moved {low_confidence_omitted} finding(s) below the minimum confidence into limitations."
        )
        omitted.append(OmittedScope(reason="minimum_confidence", count=low_confidence_omitted))
    if refactors_omitted:
        omitted.append(OmittedScope(reason="low_risk_refactor_policy", count=refactors_omitted))
    test_index = build_test_index(repo, head_commit, config)
    warnings.extend(test_index.warnings)
    mapped_by_index = map_candidate_tests(reportable, test_index, config)
    behaviors: list[BehaviorChange] = []
    tests_by_behavior: dict[str, list[Any]] = {}
    fallback_mode = not interpreted.status.available
    for index, candidate in enumerate(reportable, start=1):
        candidate_tests = mapped_by_index.get(index - 1, [])
        risk_score, risk, explanation = score_risk(candidate, candidate_tests, config)
        confidence = confidence_by_index[id(candidate)]
        presentation = (
            Presentation.REVIEW_QUESTION
            if risk in {RiskLabel.HIGH, RiskLabel.CRITICAL}
            and confidence < config.rules.review_question_confidence
            else Presentation.FINDING
        )
        origin = candidate.origin
        if fallback_mode and origin is Origin.DETERMINISTIC:
            origin = Origin.DETERMINISTIC_FALLBACK
        behavior = BehaviorChange(
            id=f"bc-{index:03d}",
            category=candidate.category,
            summary=candidate.summary,
            observable_impact=candidate.observable_impact,
            risk=risk,
            risk_score=risk_score,
            confidence=confidence,
            evidence=candidate.evidence,
            assumptions=candidate.assumptions,
            presentation=presentation,
            origin=origin,
            score_explanation=explanation,
        )
        behaviors.append(behavior)
        tests_by_behavior[behavior.id] = candidate_tests
    obligations, omitted_obligations = generate_obligations(
        behaviors,
        tests_by_behavior,
        test_index.incomplete,
        config,
        interpreted.suggestions,
    )
    if omitted_obligations:
        omitted.append(OmittedScope(reason="global_obligation_limit", count=omitted_obligations))
        warnings.append(
            f"Omitted {omitted_obligations} lower-priority obligation(s) due to the global cap."
        )
    if behaviors:
        highest = max(behaviors, key=lambda item: item.risk_score)
        overall_risk = highest.risk
        overall_score = highest.risk_score
        obligation_weights = Counter(
            behavior_id
            for obligation in obligations
            for behavior_id in obligation.behavior_change_ids
        )
        total_weight = sum(max(1, obligation_weights[item.id]) for item in behaviors)
        overall_confidence = round(
            sum(item.confidence * max(1, obligation_weights[item.id]) for item in behaviors)
            / total_weight,
            3,
        )
    else:
        overall_risk = RiskLabel.LOW
        overall_score = 0
        overall_confidence = 1.0
    risk_counts = {label: 0 for label in RiskLabel}
    for behavior in behaviors:
        risk_counts[behavior.risk] += 1
    limitations = [
        "Candidate test mapping is static and does not prove runtime coverage.",
        "Only committed Python source at the resolved refs was inspected.",
        "Repository code and tests were not imported, executed, built, installed, or modified.",
    ]
    if not collection.files:
        limitations.append("The bounded diff contained no included changed Python source.")
    elif not ast_result.deltas:
        limitations.append(
            "The included Python change contained no reportable behavior-bearing structural delta."
        )
    if low_confidence_omitted:
        limitations.append(
            f"{low_confidence_omitted} low-confidence finding(s) were not presented as facts."
        )
    if ast_result.failed_files:
        limitations.append(
            f"{ast_result.failed_files} changed Python file(s) had incomplete parser context."
        )
    if collection.truncated:
        limitations.append(
            "Only prioritized critical-path scope was analyzed due to resource limits."
        )
    if interpreted.omitted_batches or interpreted.truncated_evidence_symbols:
        limitations.append("Some optional model interpretation context was omitted or truncated.")
    if fallback_mode and deterministic:
        limitations.append("LLM interpretation was unavailable; deterministic fallback was used.")
    analysis = AnalysisResult(
        analysis_id=f"sdw_{uuid4().hex}",
        repository=RepositoryIdentity(
            base_ref=request.base_ref,
            head_ref=request.head_ref,
            base_commit=base_commit,
            head_commit=head_commit,
        ),
        summary=Summary(
            changed_files=collection.changed_files_total,
            changed_symbols=changed_symbols,
            behavior_changes=len(behaviors),
            test_obligations=len(obligations),
            overall_risk=overall_risk,
            risk_score=overall_score,
            overall_confidence=overall_confidence,
            risk_counts=risk_counts,
        ),
        scope=ScopeMetadata(
            changed_files_total=collection.changed_files_total,
            analyzed_files=sorted(item.path for item in collection.files),
            excluded_counts=collection.excluded_counts,
            omitted=omitted,
            changed_lines=collection.changed_lines,
            changed_symbols=changed_symbols,
            truncated=scope_truncated or bool(omitted_obligations),
        ),
        behavior_changes=behaviors,
        test_obligations=obligations,
        warnings=sorted(set(warnings)),
        limitations=limitations,
        llm=interpreted.status if deterministic else LlmStatus(),
        deterministic_mode=fallback_mode,
    )
    return render_transport(analysis, request.output_format)
