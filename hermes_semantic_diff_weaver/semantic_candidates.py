"""Deterministic, evidence-backed semantic candidate rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ast_diff import StructuralDelta
from .models import BehaviorCategory, Evidence, Origin

AUTH_TERMS = ("auth", "permission", "permit", "role", "owner", "identity", "principal")
VALIDATION_TERMS = ("valid", "validate", "validator", "allowed", "reject", "accept")
RETRY_TERMS = ("retry", "attempt", "timeout", "sleep", "backoff", "deadline", "limit")
SIDE_EFFECT_TERMS = (
    "save",
    "write",
    "delete",
    "remove",
    "commit",
    "publish",
    "send",
    "notify",
    "emit",
    "dispatch",
    "persist",
    "enqueue",
)


@dataclass
class SemanticCandidate:
    category: BehaviorCategory
    summary: str
    observable_impact: str
    evidence: list[Evidence]
    confidence_baseline: float
    assumptions: list[str] = field(default_factory=list)
    origin: Origin = Origin.DETERMINISTIC
    rule_ids: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.evidence[0].path

    @property
    def symbol(self) -> str:
        return self.evidence[0].symbol or "<module>"


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in terms)


def _classification(
    delta: StructuralDelta,
) -> tuple[BehaviorCategory, str, str, float, list[str], str]:
    combined = " ".join(filter(None, (delta.old, delta.new, delta.symbol)))
    if delta.kind == "comparison_change":
        if _contains(combined, RETRY_TERMS):
            return (
                BehaviorCategory.RETRY_TIMEOUT,
                "A retry, timeout, or limit boundary appears to have changed.",
                "The exact attempt, timeout, or termination boundary may now produce a different outcome.",
                0.90,
                [],
                "SDW-RULE-RETRY-BOUNDARY",
            )
        return (
            BehaviorCategory.BOUNDARY,
            "A comparison boundary appears to have changed.",
            "Inputs at or adjacent to the changed boundary may now be accepted, rejected, or routed differently.",
            0.94,
            [],
            "SDW-RULE-BOUNDARY",
        )
    if delta.kind == "signature_change":
        if delta.metadata.get("default_changed"):
            return (
                BehaviorCategory.DEFAULT_BEHAVIOR,
                "A callable default argument appears to have changed.",
                "Callers that omit the affected argument may now observe a different result or path.",
                0.94,
                [],
                "SDW-RULE-DEFAULT",
            )
        return (
            BehaviorCategory.OUTPUT_CONTRACT,
            "A callable signature appears to have changed.",
            "Existing callers may need to supply different arguments or handle a changed callable contract.",
            0.88,
            [],
            "SDW-RULE-SIGNATURE",
        )
    if delta.kind in {"raise_change", "exception_handler_change"}:
        return (
            BehaviorCategory.ERROR_HANDLING,
            "An exception or error-handling path appears to have changed.",
            "The same failure trigger may now propagate, be swallowed, or expose a different error.",
            0.91,
            [],
            "SDW-RULE-ERROR",
        )
    if delta.kind == "return_change":
        return (
            BehaviorCategory.OUTPUT_CONTRACT,
            "A visible return expression or shape appears to have changed.",
            "Consumers may observe a different value, status, field, or container shape.",
            0.88,
            [],
            "SDW-RULE-RETURN",
        )
    if delta.kind == "assignment_change":
        return (
            BehaviorCategory.STATE_TRANSITION,
            "A state assignment or transition appears to have changed.",
            "The operation may now enter, retain, or reject a different observable state.",
            0.82,
            [],
            "SDW-RULE-STATE",
        )
    if delta.kind == "loop_change":
        return (
            BehaviorCategory.RETRY_TIMEOUT,
            "A loop, retry, or stop condition appears to have changed.",
            "The operation may perform a different number of attempts or terminate under different conditions.",
            0.84,
            [],
            "SDW-RULE-LOOP",
        )
    if delta.kind == "condition_change":
        if any(operator in combined for operator in ("<", ">", "==", "!=")):
            category = (
                BehaviorCategory.RETRY_TIMEOUT
                if _contains(combined, RETRY_TERMS)
                else BehaviorCategory.BOUNDARY
            )
            return (
                category,
                "A condition boundary appears to have changed.",
                "Inputs at or adjacent to the changed condition may now follow a different path.",
                0.88,
                [],
                "SDW-RULE-CONDITION-BOUNDARY",
            )
        if _contains(combined, AUTH_TERMS):
            return (
                BehaviorCategory.AUTHORIZATION,
                "An authorization-related guard appears to have changed.",
                "Allowed and denied principals may no longer follow the same path.",
                0.70,
                ["Authorization meaning is inferred from conservative names and guard structure."],
                "SDW-RULE-AUTH-GUARD",
            )
        if _contains(combined, VALIDATION_TERMS):
            return (
                BehaviorCategory.VALIDATION,
                "An input validation condition appears to have changed.",
                "Some inputs may now be newly accepted or newly rejected.",
                0.74,
                ["Validation meaning is inferred from conservative names and condition structure."],
                "SDW-RULE-VALIDATION-GUARD",
            )
        if _contains(combined, RETRY_TERMS):
            return (
                BehaviorCategory.RETRY_TIMEOUT,
                "A retry or termination predicate appears to have changed.",
                "Recoverable, terminal, or exact-limit cases may now perform a different number of attempts.",
                0.78,
                [],
                "SDW-RULE-RETRY-GUARD",
            )
        return (
            BehaviorCategory.UNKNOWN,
            "A control-flow condition changed without enough local contract context.",
            "Competing input cases may now follow a different branch; the observable effect needs review.",
            0.55,
            ["The surrounding runtime contract is unavailable to static analysis."],
            "SDW-RULE-UNKNOWN-CONDITION",
        )
    if delta.kind == "call_change":
        if _contains(combined, AUTH_TERMS):
            return (
                BehaviorCategory.AUTHORIZATION,
                "An authorization-related interaction appears to have changed.",
                "An allowed or denied principal may now receive a different outcome.",
                0.68,
                ["Authorization meaning is inferred from call names and structure."],
                "SDW-RULE-AUTH-CALL",
            )
        if _contains(combined, VALIDATION_TERMS):
            return (
                BehaviorCategory.VALIDATION,
                "A validator interaction appears to have changed.",
                "New input classes may be accepted or rejected.",
                0.70,
                ["Validation meaning is inferred from call names and structure."],
                "SDW-RULE-VALIDATION-CALL",
            )
        if _contains(combined, RETRY_TERMS):
            return (
                BehaviorCategory.RETRY_TIMEOUT,
                "A retry, delay, or timeout interaction appears to have changed.",
                "Attempt count, wait behavior, or termination may differ for failures.",
                0.72,
                ["Retry meaning is inferred from call names and structure."],
                "SDW-RULE-RETRY-CALL",
            )
        if _contains(combined, SIDE_EFFECT_TERMS):
            return (
                BehaviorCategory.SIDE_EFFECT,
                "An external or persistent side-effect call appears to have changed.",
                "An observable write, event, notification, or dispatch may now occur or be absent.",
                0.70,
                ["Side-effect meaning is inferred from conservative call-name signals."],
                "SDW-RULE-SIDE-EFFECT",
            )
        return (
            BehaviorCategory.DEPENDENCY_INTERACTION,
            "A dependency call or its arguments appear to have changed.",
            "Dependency success, failure, or unexpected responses may now be handled differently.",
            0.66,
            ["The dependency contract is not available to static analysis."],
            "SDW-RULE-DEPENDENCY",
        )
    if delta.kind in {"call_order_change", "condition_order_change", "statement_order_change"}:
        return (
            BehaviorCategory.ORDERING,
            "Execution or call ordering appears to have changed.",
            "Sequence-sensitive cases or competing conditions may now produce a different outcome.",
            0.72,
            [],
            "SDW-RULE-ORDERING",
        )
    if delta.kind == "structural_refactor":
        return (
            BehaviorCategory.REFACTOR,
            "The changed symbol retains the same normalized behavior-bearing structure.",
            "No material observable behavior change is apparent from the normalized syntax.",
            0.82,
            [],
            "SDW-RULE-REFACTOR",
        )
    if delta.kind == "decorator_change" and _contains(combined, AUTH_TERMS):
        return (
            BehaviorCategory.AUTHORIZATION,
            "An authorization-related decorator appears to have changed.",
            "Access to the decorated callable may now differ by principal.",
            0.72,
            ["Authorization meaning is inferred from decorator naming."],
            "SDW-RULE-AUTH-DECORATOR",
        )
    return (
        BehaviorCategory.UNKNOWN,
        "A material structural change cannot be classified reliably from local evidence.",
        "An observable outcome may have changed; the affected contract needs review.",
        0.50,
        ["Static syntax does not expose the complete runtime contract."],
        "SDW-RULE-UNKNOWN",
    )


def build_candidates(deltas: list[StructuralDelta]) -> list[SemanticCandidate]:
    """Apply stable rules, create evidence IDs, and merge same-symbol categories."""
    grouped: dict[tuple[str, str, BehaviorCategory], SemanticCandidate] = {}
    for index, delta in enumerate(deltas, start=1):
        category, summary, impact, baseline, assumptions, rule_id = _classification(delta)
        evidence = Evidence(
            id=f"ev-{index:03d}",
            path=delta.path,
            symbol=delta.symbol,
            old_lines=delta.old_lines,
            new_lines=delta.new_lines,
            hunk_id=delta.hunk_id,
            old=delta.old,
            new=delta.new,
            kind=delta.kind,
            parser_complete=delta.parser_complete,
        )
        key = (delta.path, delta.symbol, category)
        if key in grouped:
            current = grouped[key]
            current.evidence.append(evidence)
            current.confidence_baseline = max(current.confidence_baseline, baseline)
            current.assumptions = sorted(set([*current.assumptions, *assumptions]))
            current.rule_ids.append(rule_id)
        else:
            grouped[key] = SemanticCandidate(
                category=category,
                summary=summary,
                observable_impact=impact,
                evidence=[evidence],
                confidence_baseline=baseline,
                assumptions=assumptions,
                rule_ids=[rule_id],
            )
    return sorted(grouped.values(), key=lambda item: (item.path, item.symbol, item.category.value))
