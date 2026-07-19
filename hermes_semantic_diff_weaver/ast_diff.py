"""Static Python AST extraction, conservative symbol matching, and structural deltas."""

from __future__ import annotations

import ast
import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .git_diff import ChangedFile, Hunk
from .models import LineRange
from .path_policy import redact_text


def _compact(node: ast.AST | None, limit: int = 500) -> str:
    if node is None:
        return "None"
    try:
        return redact_text(ast.unparse(node), max_chars=limit)
    except (AttributeError, ValueError):
        return type(node).__name__


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return "<dynamic>"


def _decorator_name(node: ast.AST) -> str:
    """Return only a bounded decorator name, never its untrusted arguments."""
    target = node.func if isinstance(node, ast.Call) else node
    return redact_text(_call_name(target), max_chars=120)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Normalize the complete callable signature, including its return annotation."""
    signature = f"({_compact(node.args, 900)})"
    if node.returns is not None:
        signature += f" -> {_compact(node.returns, 300)}"
    if node.type_comment:
        signature += f" # type: {redact_text(node.type_comment, max_chars=300)}"
    return signature


def _body_fingerprint(body: list[ast.stmt]) -> str:
    material = _behavior_body(body)
    dump = ast.dump(ast.Module(body=material, type_ignores=[]), include_attributes=False)
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


def _behavior_body(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _node_inventory(body: list[ast.stmt]) -> tuple[tuple[str, int], ...]:
    module = ast.Module(body=_behavior_body(body), type_ignores=[])
    counts = Counter(type(node).__name__ for node in ast.walk(module))
    return tuple(sorted(counts.items()))


class FeatureVisitor(ast.NodeVisitor):
    """Collect bounded behavior-bearing syntax while avoiding nested symbol bodies."""

    def __init__(self, root: ast.AST) -> None:
        self.root = root
        self.comparisons: list[tuple[str, int]] = []
        self.conditions: list[tuple[str, int]] = []
        self.raises: list[tuple[str, int]] = []
        self.handlers: list[tuple[str, int]] = []
        self.calls: list[tuple[str, int]] = []
        self.returns: list[tuple[str, int]] = []
        self.assignments: list[tuple[str, int]] = []
        self.loops: list[tuple[str, int]] = []
        self.contexts: list[tuple[str, int]] = []
        self.statement_order: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        operators = ",".join(type(item).__name__ for item in node.ops)
        self.comparisons.append((f"{_compact(node)} [{operators}]", node.lineno))
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.conditions.append((_compact(node.test), node.lineno))
        self.statement_order.append(f"if:{_compact(node.test, 120)}")
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.conditions.append((_compact(node.test), node.lineno))
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.conditions.append((_compact(node.test), node.lineno))
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.raises.append((_compact(node.exc), node.lineno))
        self.statement_order.append(f"raise:{_compact(node.exc, 120)}")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.handlers.append((_compact(node.type), node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        positional = [_compact(item, 100) for item in node.args[:5]]
        keywords = [f"{item.arg or '**'}={_compact(item.value, 100)}" for item in node.keywords[:5]]
        arguments = ", ".join([*positional, *keywords])
        self.calls.append((f"{name}({arguments})", node.lineno))
        self.statement_order.append(f"call:{name}")
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        self.returns.append((_compact(node.value), node.lineno))
        self.statement_order.append(f"return:{_compact(node.value, 120)}")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        targets = ", ".join(_compact(item, 100) for item in node.targets)
        self.assignments.append((f"{targets} = {_compact(node.value, 250)}", node.lineno))
        self.statement_order.append(f"assign:{targets}")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        value = f"{_compact(node.target, 100)} = {_compact(node.value, 250)}"
        self.assignments.append((value, node.lineno))
        self.statement_order.append(f"assign:{_compact(node.target, 100)}")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        value = (
            f"{_compact(node.target, 100)} {type(node.op).__name__}= {_compact(node.value, 250)}"
        )
        self.assignments.append((value, node.lineno))
        self.statement_order.append(f"assign:{_compact(node.target, 100)}")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.loops.append(
            (f"for {_compact(node.target, 100)} in {_compact(node.iter, 250)}", node.lineno)
        )
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.loops.append(
            (f"async for {_compact(node.target, 100)} in {_compact(node.iter, 250)}", node.lineno)
        )
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.loops.append((f"while {_compact(node.test, 250)}", node.lineno))
        self.conditions.append((_compact(node.test), node.lineno))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        names = ", ".join(_compact(item.context_expr, 150) for item in node.items)
        self.contexts.append((names, node.lineno))
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        names = ", ".join(_compact(item.context_expr, 150) for item in node.items)
        self.contexts.append((names, node.lineno))
        self.generic_visit(node)


@dataclass
class SymbolSnapshot:
    qualified_name: str
    kind: str
    start: int
    end: int
    signature: str
    default_map: dict[str, str]
    decorators: tuple[str, ...]
    fingerprint: str
    features: dict[str, tuple[tuple[str, int], ...]]
    statement_order: tuple[str, ...]
    node_inventory: tuple[tuple[str, int], ...]
    match_ambiguous: bool = False

    @property
    def signature_shape(self) -> str:
        return reparameterize(self.signature)


def reparameterize(signature: str) -> str:
    """Normalize identifiers while preserving argument structure for rename matching."""
    result: list[str] = []
    in_identifier = False
    for char in signature:
        if char.isalnum() or char == "_":
            if not in_identifier:
                result.append("_")
                in_identifier = True
        else:
            result.append(char)
            in_identifier = False
    return "".join(result)


def _defaults(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
    positional = [*node.args.posonlyargs, *node.args.args]
    result: dict[str, str] = {}
    if node.args.defaults:
        for argument, default in zip(
            positional[-len(node.args.defaults) :], node.args.defaults, strict=True
        ):
            result[argument.arg] = _compact(default, 200)
    for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        if default is not None:
            result[argument.arg] = _compact(default, 200)
    return result


def _snapshot(node: ast.AST, qualified_name: str, kind: str) -> SymbolSnapshot:
    body = list(getattr(node, "body", []))
    visitor = FeatureVisitor(node)
    visitor.visit(node)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        signature = _function_signature(node)
        defaults = _defaults(node)
        decorators = tuple(_decorator_name(item) for item in node.decorator_list)
    elif isinstance(node, ast.ClassDef):
        signature = f"bases({', '.join(_compact(item, 120) for item in node.bases)})"
        defaults = {}
        decorators = tuple(_decorator_name(item) for item in node.decorator_list)
    else:
        signature = "module"
        defaults = {}
        decorators = ()
    feature_names = (
        "comparisons",
        "conditions",
        "raises",
        "handlers",
        "calls",
        "returns",
        "assignments",
        "loops",
        "contexts",
    )
    return SymbolSnapshot(
        qualified_name=qualified_name,
        kind=kind,
        start=getattr(node, "lineno", 1),
        end=getattr(node, "end_lineno", max(1, len(body))),
        signature=signature,
        default_map=defaults,
        decorators=decorators,
        fingerprint=_body_fingerprint(body),
        features={name: tuple(getattr(visitor, name)) for name in feature_names},
        statement_order=tuple(visitor.statement_order),
        node_inventory=_node_inventory(body),
    )


def extract_symbols(source: str) -> list[SymbolSnapshot]:
    tree = ast.parse(source, type_comments=True)
    symbols: list[SymbolSnapshot] = []

    def walk(body: list[ast.stmt], prefix: str, *, parent_is_class: bool = False) -> None:
        module_body: list[ast.stmt] = []
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                name = f"{prefix}.{statement.name}" if prefix else statement.name
                class_shell = ast.ClassDef(
                    name=statement.name,
                    bases=statement.bases,
                    keywords=statement.keywords,
                    body=[
                        item
                        for item in statement.body
                        if not isinstance(
                            item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                        )
                    ],
                    decorator_list=statement.decorator_list,
                )
                ast.copy_location(class_shell, statement)
                class_shell.end_lineno = statement.end_lineno
                symbols.append(_snapshot(class_shell, name, "class"))
                walk(statement.body, name, parent_is_class=True)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}.{statement.name}" if prefix else statement.name
                if parent_is_class:
                    kind = (
                        "async_method" if isinstance(statement, ast.AsyncFunctionDef) else "method"
                    )
                else:
                    kind = (
                        "async_function"
                        if isinstance(statement, ast.AsyncFunctionDef)
                        else "function"
                    )
                symbols.append(_snapshot(statement, name, kind))
                nested = [
                    item
                    for item in statement.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                ]
                walk(nested, name)
            else:
                module_body.append(statement)
        if not prefix:
            module = ast.Module(body=module_body, type_ignores=[])
            snapshot = _snapshot(module, "<module>", "module")
            snapshot.start = 1
            snapshot.end = max(1, len(source.splitlines()))
            symbols.append(snapshot)

    walk(tree.body, "")
    return symbols


@dataclass
class StructuralDelta:
    path: str
    symbol: str
    kind: str
    old: str | None
    new: str | None
    old_lines: LineRange | None
    new_lines: LineRange | None
    hunk_id: str | None
    parser_complete: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AstAnalysis:
    deltas: list[StructuralDelta]
    warnings: list[str]
    parsed_files: int
    failed_files: int
    changed_symbols: int


def _overlaps(start: int, end: int, hunk_start: int, hunk_count: int) -> bool:
    if hunk_count == 0:
        return start <= hunk_start <= end + 1
    return start <= hunk_start + hunk_count - 1 and hunk_start <= end


def _matching_hunk(
    old: SymbolSnapshot | None,
    new: SymbolSnapshot | None,
    *,
    old_hunks: list[Hunk],
    new_hunks: list[Hunk],
    old_path: str,
    new_path: str,
) -> str | None:
    for hunk in new_hunks:
        if new and _overlaps(new.start, new.end, hunk.new_start, hunk.new_count):
            return f"{new_path}#{hunk.id}"
    for hunk in old_hunks:
        if old and _overlaps(old.start, old.end, hunk.old_start, hunk.old_count):
            return f"{old_path}#{hunk.id}"
    return None


def _summary(values: Iterable[tuple[str, int]]) -> str | None:
    material = [item[0] for item in values]
    return redact_text("; ".join(material), max_chars=1500) if material else None


def _ranges(
    old: SymbolSnapshot | None, new: SymbolSnapshot | None
) -> tuple[LineRange | None, LineRange | None]:
    old_range = LineRange(start=old.start, end=old.end) if old else None
    new_range = LineRange(start=new.start, end=new.end) if new else None
    return old_range, new_range


def _delta(
    path: str,
    old: SymbolSnapshot | None,
    new: SymbolSnapshot | None,
    hunk_id: str | None,
    kind: str,
    old_value: str | None,
    new_value: str | None,
    **metadata: Any,
) -> StructuralDelta:
    old_lines, new_lines = _ranges(old, new)
    return StructuralDelta(
        path=path,
        symbol=(new or old).qualified_name,  # type: ignore[union-attr]
        kind=kind,
        old=redact_text(old_value, max_chars=1500) if old_value else None,
        new=redact_text(new_value, max_chars=1500) if new_value else None,
        old_lines=old_lines,
        new_lines=new_lines,
        hunk_id=hunk_id,
        metadata=metadata,
    )


def _compare_symbol(
    path: str,
    old: SymbolSnapshot | None,
    new: SymbolSnapshot | None,
    hunks: list[Hunk],
    *,
    old_path: str | None = None,
    new_path: str | None = None,
    old_hunks: list[Hunk] | None = None,
    new_hunks: list[Hunk] | None = None,
) -> list[StructuralDelta]:
    effective_old_path = old_path or path
    effective_new_path = new_path or path
    hunk_id = _matching_hunk(
        old,
        new,
        old_hunks=old_hunks if old_hunks is not None else hunks,
        new_hunks=new_hunks if new_hunks is not None else hunks,
        old_path=effective_old_path,
        new_path=effective_new_path,
    )
    if hunk_id is None:
        return []
    if old is None:
        return [
            _delta(
                path,
                old,
                new,
                hunk_id,
                "symbol_added",
                None,
                new.signature,
                ambiguous_match=new.match_ambiguous,
            )
        ]
    if new is None:
        return [
            _delta(
                path,
                old,
                new,
                hunk_id,
                "symbol_removed",
                old.signature,
                None,
                ambiguous_match=old.match_ambiguous,
            )
        ]
    result: list[StructuralDelta] = []
    if old.signature != new.signature:
        result.append(
            _delta(
                path,
                old,
                new,
                hunk_id,
                "signature_change",
                old.signature,
                new.signature,
                default_changed=old.default_map != new.default_map,
                old_defaults=old.default_map,
                new_defaults=new.default_map,
            )
        )
    if old.decorators != new.decorators:
        result.append(
            _delta(
                path,
                old,
                new,
                hunk_id,
                "decorator_change",
                ", ".join(old.decorators),
                ", ".join(new.decorators),
            )
        )
    for feature, kind in (
        ("comparisons", "comparison_change"),
        ("conditions", "condition_change"),
        ("raises", "raise_change"),
        ("handlers", "exception_handler_change"),
        ("returns", "return_change"),
        ("assignments", "assignment_change"),
        ("loops", "loop_change"),
        ("contexts", "context_manager_change"),
    ):
        old_values = [item[0] for item in old.features[feature]]
        new_values = [item[0] for item in new.features[feature]]
        if old_values != new_values:
            effective_kind = (
                "condition_order_change"
                if feature == "conditions" and sorted(old_values) == sorted(new_values)
                else kind
            )
            result.append(
                _delta(
                    path,
                    old,
                    new,
                    hunk_id,
                    effective_kind,
                    _summary(old.features[feature]),
                    _summary(new.features[feature]),
                )
            )
    old_calls = old.features["calls"]
    new_calls = new.features["calls"]
    old_names = [item[0] for item in old_calls]
    new_names = [item[0] for item in new_calls]
    if old_names != new_names:
        kind = "call_order_change" if sorted(old_names) == sorted(new_names) else "call_change"
        result.append(
            _delta(
                path,
                old,
                new,
                hunk_id,
                kind,
                "; ".join(old_names),
                "; ".join(new_names),
                old_calls=[item.split("(", 1)[0] for item in old_names],
                new_calls=[item.split("(", 1)[0] for item in new_names],
            )
        )
    result_kinds = {item.kind for item in result}
    if "raise_change" in result_kinds and "call_change" in result_kinds:
        result = [item for item in result if item.kind != "call_change"]
        result_kinds.remove("call_change")
    if "return_change" in result_kinds and "comparison_change" in result_kinds:
        result = [item for item in result if item.kind != "return_change"]
    elif "return_change" in result_kinds and "call_change" in result_kinds:
        return_values = [
            item[0].lstrip() for item in (*old.features["returns"], *new.features["returns"])
        ]
        if return_values and all(
            "(" in value and not value.startswith(("{", "[", "(")) for value in return_values
        ):
            result = [item for item in result if item.kind != "return_change"]
    if old.statement_order != new.statement_order and not any(
        item.kind
        in {
            "call_order_change",
            "comparison_change",
            "condition_change",
            "condition_order_change",
            "raise_change",
            "return_change",
            "assignment_change",
            "loop_change",
        }
        for item in result
    ):
        result.append(
            _delta(
                path,
                old,
                new,
                hunk_id,
                "statement_order_change",
                "; ".join(old.statement_order),
                "; ".join(new.statement_order),
            )
        )
    if not result and (
        old.qualified_name != new.qualified_name or old.fingerprint == new.fingerprint
    ):
        result.append(
            _delta(
                path,
                old,
                new,
                hunk_id,
                "structural_refactor",
                old.qualified_name,
                new.qualified_name,
                materiality=round(max(0.0, 1.0 - _symbol_similarity(old, new)), 3),
            )
        )
    elif old.fingerprint != new.fingerprint and not result:
        result.append(
            _delta(path, old, new, hunk_id, "unknown_structure", "body changed", "body changed")
        )
    if effective_old_path != effective_new_path:
        for item in result:
            item.metadata.update(old_path=effective_old_path, new_path=effective_new_path)
    return result


def _multiset_similarity(
    left: tuple[tuple[str, int], ...], right: tuple[tuple[str, int], ...]
) -> float:
    left_counts = dict(left)
    right_counts = dict(right)
    keys = left_counts.keys() | right_counts.keys()
    total = sum(max(left_counts.get(key, 0), right_counts.get(key, 0)) for key in keys)
    if total == 0:
        return 1.0
    overlap = sum(min(left_counts.get(key, 0), right_counts.get(key, 0)) for key in keys)
    return overlap / total


def _set_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _symbol_similarity(old: SymbolSnapshot, new: SymbolSnapshot) -> float:
    if old.kind != new.kind:
        return 0.0
    old_parent = old.qualified_name.rpartition(".")[0]
    new_parent = new.qualified_name.rpartition(".")[0]
    signature = SequenceMatcher(None, old.signature_shape, new.signature_shape).ratio()
    calls = _set_similarity(
        {value.split("(", 1)[0] for value, _ in old.features["calls"]},
        {value.split("(", 1)[0] for value, _ in new.features["calls"]},
    )
    old_feature_counts = tuple(sorted((name, len(values)) for name, values in old.features.items()))
    new_feature_counts = tuple(sorted((name, len(values)) for name, values in new.features.items()))
    order = _set_similarity(
        {item.split(":", 1)[0] for item in old.statement_order},
        {item.split(":", 1)[0] for item in new.statement_order},
    )
    return min(
        1.0,
        signature * 0.20
        + (0.10 if old_parent == new_parent else 0.0)
        + _multiset_similarity(old.node_inventory, new.node_inventory) * 0.25
        + calls * 0.15
        + _multiset_similarity(old_feature_counts, new_feature_counts) * 0.15
        + order * 0.10
        + (0.05 if old.fingerprint == new.fingerprint else 0.0),
    )


def _match_symbols(
    old_symbols: list[SymbolSnapshot], new_symbols: list[SymbolSnapshot]
) -> tuple[list[tuple[SymbolSnapshot | None, SymbolSnapshot | None]], list[str]]:
    """Match symbols within one file while preserving overload-style duplicate names."""
    pairs: list[tuple[SymbolSnapshot | None, SymbolSnapshot | None]] = []
    warnings: list[str] = []
    old_by_name: dict[str, list[SymbolSnapshot]] = defaultdict(list)
    new_by_name: dict[str, list[SymbolSnapshot]] = defaultdict(list)
    for item in old_symbols:
        old_by_name[item.qualified_name].append(item)
    for item in new_symbols:
        new_by_name[item.qualified_name].append(item)
    matched_old: set[int] = set()
    matched_new: set[int] = set()
    for name in sorted(old_by_name.keys() & new_by_name.keys()):
        old_group = sorted(old_by_name[name], key=lambda item: item.start)
        new_group = sorted(new_by_name[name], key=lambda item: item.start)
        # Exact definition shapes preserve overloads even when their order changes.
        for old in old_group:
            possible = [
                new
                for new in new_group
                if id(new) not in matched_new
                and old.kind == new.kind
                and old.signature == new.signature
                and old.fingerprint == new.fingerprint
            ]
            if len(possible) == 1:
                new = possible[0]
                pairs.append((old, new))
                matched_old.add(id(old))
                matched_new.add(id(new))
        remaining_old_same = [item for item in old_group if id(item) not in matched_old]
        remaining_new_same = [item for item in new_group if id(item) not in matched_new]
        # Exact qualified names are the authoritative next pass. Source order disambiguates
        # overload-like duplicates without discarding either definition.
        for old, new in zip(remaining_old_same, remaining_new_same, strict=False):
            pairs.append((old, new))
            matched_old.add(id(old))
            matched_new.add(id(new))
        if len(old_group) != len(new_group) and max(len(old_group), len(new_group)) > 1:
            warnings.append(
                f"Overload-like definition count changed for {name!r}; unmatched definitions "
                "were retained explicitly."
            )
    remaining_old = sorted(
        (item for item in old_symbols if id(item) not in matched_old),
        key=lambda item: (item.qualified_name, item.start),
    )
    remaining_new = sorted(
        (item for item in new_symbols if id(item) not in matched_new),
        key=lambda item: (item.qualified_name, item.start),
    )
    candidates: dict[str, list[SymbolSnapshot]] = defaultdict(list)
    for item in remaining_new:
        candidates[f"{item.kind}:{item.signature_shape}:{item.fingerprint}"].append(item)
    unresolved: list[SymbolSnapshot] = []
    for old in remaining_old:
        key = f"{old.kind}:{old.signature_shape}:{old.fingerprint}"
        possible = [item for item in candidates.get(key, []) if id(item) not in matched_new]
        if len(possible) == 1:
            new = possible[0]
            pairs.append((old, new))
            matched_old.add(id(old))
            matched_new.add(id(new))
        elif len(possible) > 1:
            old.match_ambiguous = True
            for item in possible:
                item.match_ambiguous = True
            warnings.append(
                f"Ambiguous symbol match for {old.qualified_name!r}; treated conservatively."
            )
        else:
            unresolved.append(old)
    for old in unresolved:
        scored = sorted(
            (
                (_symbol_similarity(old, new), new)
                for new in remaining_new
                if id(new) not in matched_new
            ),
            key=lambda item: (-item[0], item[1].qualified_name, item[1].start),
        )
        plausible = [item for item in scored if item[0] >= 0.82]
        if not plausible:
            continue
        if len(plausible) > 1 and plausible[0][0] - plausible[1][0] <= 0.03:
            old.match_ambiguous = True
            for _, item in plausible:
                item.match_ambiguous = True
            warnings.append(
                f"Ambiguous similarity match for {old.qualified_name!r}; treated conservatively."
            )
            continue
        new = plausible[0][1]
        pairs.append((old, new))
        matched_old.add(id(old))
        matched_new.add(id(new))
    for old in remaining_old:
        if id(old) not in matched_old:
            pairs.append((old, None))
    for new in remaining_new:
        if id(new) not in matched_new:
            pairs.append((None, new))
    return pairs, warnings


def _match_cross_file_symbols(
    removed: list[tuple[SymbolSnapshot, ChangedFile]],
    added: list[tuple[SymbolSnapshot, ChangedFile]],
) -> tuple[
    list[tuple[SymbolSnapshot, ChangedFile, SymbolSnapshot, ChangedFile]],
    list[tuple[SymbolSnapshot, ChangedFile]],
    list[tuple[SymbolSnapshot, ChangedFile]],
    list[str],
]:
    """Correlate conservative symbol moves between distinct changed files."""
    pairs: list[tuple[SymbolSnapshot, ChangedFile, SymbolSnapshot, ChangedFile]] = []
    warnings: list[str] = []
    matched_old: set[int] = set()
    matched_new: set[int] = set()

    def available_added() -> list[tuple[SymbolSnapshot, ChangedFile]]:
        return [item for item in added if id(item[0]) not in matched_new]

    # Preserve exact qualified names across files first, but never force duplicate near-ties.
    for old, old_file in removed:
        if old.kind == "module":
            continue
        exact = [
            (new, new_file)
            for new, new_file in available_added()
            if new.kind == old.kind and new.qualified_name == old.qualified_name
        ]
        if len(exact) == 1:
            new, new_file = exact[0]
            pairs.append((old, old_file, new, new_file))
            matched_old.add(id(old))
            matched_new.add(id(new))
        elif len(exact) > 1:
            old.match_ambiguous = True
            for new, _ in exact:
                new.match_ambiguous = True
            warnings.append(
                f"Ambiguous cross-file move for {old.qualified_name!r}; treated conservatively."
            )

    # An exact signature and behavior fingerprint is strong move evidence even after a rename.
    for old, old_file in removed:
        if id(old) in matched_old or old.kind == "module":
            continue
        exact = [
            (new, new_file)
            for new, new_file in available_added()
            if new.kind == old.kind
            and new.signature_shape == old.signature_shape
            and new.fingerprint == old.fingerprint
        ]
        if len(exact) == 1:
            new, new_file = exact[0]
            pairs.append((old, old_file, new, new_file))
            matched_old.add(id(old))
            matched_new.add(id(new))
        elif len(exact) > 1:
            old.match_ambiguous = True
            for new, _ in exact:
                new.match_ambiguous = True
            warnings.append(
                f"Ambiguous cross-file fingerprint match for {old.qualified_name!r}; "
                "treated conservatively."
            )

    for old, old_file in removed:
        if id(old) in matched_old or old.kind == "module":
            continue
        scored = sorted(
            (
                (_symbol_similarity(old, new), new, new_file)
                for new, new_file in available_added()
                if new.kind != "module"
            ),
            key=lambda item: (-item[0], item[2].path, item[1].qualified_name, item[1].start),
        )
        plausible = [item for item in scored if item[0] >= 0.82]
        if not plausible:
            continue
        if len(plausible) > 1 and plausible[0][0] - plausible[1][0] <= 0.03:
            old.match_ambiguous = True
            for _, new, _ in plausible:
                new.match_ambiguous = True
            warnings.append(
                f"Ambiguous cross-file similarity match for {old.qualified_name!r}; "
                "treated conservatively."
            )
            continue
        _, new, new_file = plausible[0]
        pairs.append((old, old_file, new, new_file))
        matched_old.add(id(old))
        matched_new.add(id(new))

    unmatched_removed = [item for item in removed if id(item[0]) not in matched_old]
    unmatched_added = [item for item in added if id(item[0]) not in matched_new]
    return pairs, unmatched_removed, unmatched_added, warnings


def analyze_ast(files: list[ChangedFile]) -> AstAnalysis:
    deltas: list[StructuralDelta] = []
    warnings: list[str] = []
    parsed_files = 0
    failed_files = 0
    changed_symbol_keys: set[tuple[str, str]] = set()
    parsed: list[tuple[ChangedFile, list[SymbolSnapshot], list[SymbolSnapshot]]] = []
    for changed in files:
        path = changed.path
        try:
            old_symbols = extract_symbols(changed.old_text) if changed.old_text is not None else []
            new_symbols = extract_symbols(changed.new_text) if changed.new_text is not None else []
        except (SyntaxError, ValueError, TypeError):
            failed_files += 1
            warnings.append(
                f"Could not parse changed Python source {path!r}; analysis is incomplete."
            )
            hunk = changed.hunks[0] if changed.hunks else None
            old_lines = (
                LineRange(
                    start=max(1, hunk.old_start),
                    end=max(1, hunk.old_start + max(1, hunk.old_count) - 1),
                )
                if hunk
                else None
            )
            new_lines = (
                LineRange(
                    start=max(1, hunk.new_start),
                    end=max(1, hunk.new_start + max(1, hunk.new_count) - 1),
                )
                if hunk
                else None
            )
            deltas.append(
                StructuralDelta(
                    path=path,
                    symbol="<unparsed>",
                    kind="parse_incomplete",
                    old="Committed Python syntax could not be parsed",
                    new="Committed Python syntax could not be parsed",
                    old_lines=old_lines,
                    new_lines=new_lines,
                    hunk_id=f"{path}#{hunk.id}" if hunk else None,
                    parser_complete=False,
                    metadata={"parse_failure": True},
                )
            )
            changed_symbol_keys.add((path, "<unparsed>"))
            continue
        parsed_files += 1
        parsed.append((changed, old_symbols, new_symbols))

    removed: list[tuple[SymbolSnapshot, ChangedFile]] = []
    added: list[tuple[SymbolSnapshot, ChangedFile]] = []
    for changed, old_symbols, new_symbols in parsed:
        path = changed.path
        pairs, match_warnings = _match_symbols(old_symbols, new_symbols)
        warnings.extend(match_warnings)
        for old, new in pairs:
            if old is None:
                added.append((new, changed))  # type: ignore[arg-type]
                continue
            if new is None:
                removed.append((old, changed))
                continue
            symbol_deltas = _compare_symbol(
                path,
                old,
                new,
                changed.hunks,
                old_path=changed.old_path or path,
                new_path=changed.new_path or path,
            )
            if symbol_deltas:
                changed_symbol_keys.add((path, new.qualified_name))
                deltas.extend(symbol_deltas)

    cross_pairs, removed, added, cross_warnings = _match_cross_file_symbols(removed, added)
    warnings.extend(cross_warnings)
    for old, old_file, new, new_file in cross_pairs:
        path = new_file.path
        symbol_deltas = _compare_symbol(
            path,
            old,
            new,
            new_file.hunks,
            old_path=old_file.old_path or old_file.path,
            new_path=new_file.new_path or new_file.path,
            old_hunks=old_file.hunks,
            new_hunks=new_file.hunks,
        )
        if symbol_deltas:
            changed_symbol_keys.add((path, new.qualified_name))
            deltas.extend(symbol_deltas)
    for old, changed in removed:
        path = changed.old_path or changed.path
        symbol_deltas = _compare_symbol(
            path,
            old,
            None,
            changed.hunks,
            old_path=path,
            new_path=changed.new_path or path,
        )
        if symbol_deltas:
            changed_symbol_keys.add((path, old.qualified_name))
            deltas.extend(symbol_deltas)
    for new, changed in added:
        path = changed.new_path or changed.path
        symbol_deltas = _compare_symbol(
            path,
            None,
            new,
            changed.hunks,
            old_path=changed.old_path or path,
            new_path=path,
        )
        if symbol_deltas:
            changed_symbol_keys.add((path, new.qualified_name))
            deltas.extend(symbol_deltas)

    # A module snapshot is always recorded, but its generic add/remove/refactor evidence is
    # redundant when a more precise symbol in the same file already explains the hunk.
    detailed_paths: set[str] = set()
    for item in deltas:
        if item.symbol == "<module>":
            continue
        detailed_paths.add(item.path)
        detailed_paths.update(
            path
            for key in ("old_path", "new_path")
            if isinstance((path := item.metadata.get(key)), str)
        )
    deltas = [
        item
        for item in deltas
        if not (
            item.symbol == "<module>"
            and item.path in detailed_paths
            and item.kind in {"symbol_added", "symbol_removed", "structural_refactor"}
        )
    ]
    changed_symbol_keys = {
        key
        for key in changed_symbol_keys
        if not (key[1] == "<module>" and key[0] in detailed_paths)
    }
    return AstAnalysis(
        deltas=deltas,
        warnings=warnings,
        parsed_files=parsed_files,
        failed_files=failed_files,
        changed_symbols=len(changed_symbol_keys),
    )
