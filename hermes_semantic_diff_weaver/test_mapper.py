"""Static discovery and ranking of unverified candidate existing tests."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import ClassVar

from .git_diff import GitRepository
from .models import BehaviorCategory, CandidateTest, WeaverConfig
from .path_policy import exclusion_reason, glob_matches, redact_text
from .semantic_candidates import SemanticCandidate

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CATEGORY_TERMS = {
    BehaviorCategory.BOUNDARY: {"boundary", "limit", "threshold"},
    BehaviorCategory.VALIDATION: {"valid", "invalid", "reject", "accept"},
    BehaviorCategory.ERROR_HANDLING: {"error", "exception", "failure"},
    BehaviorCategory.STATE_TRANSITION: {"state", "transition", "status"},
    BehaviorCategory.AUTHORIZATION: {"auth", "permission", "allowed", "denied"},
    BehaviorCategory.RETRY_TIMEOUT: {"retry", "timeout", "attempt", "limit"},
    BehaviorCategory.OUTPUT_CONTRACT: {"return", "output", "response", "field"},
    BehaviorCategory.SIDE_EFFECT: {"event", "notify", "persist", "write"},
    BehaviorCategory.ORDERING: {"order", "sequence", "precedence"},
    BehaviorCategory.DEFAULT_BEHAVIOR: {"default", "omitted"},
    BehaviorCategory.DEPENDENCY_INTERACTION: {"dependency", "client", "service"},
    BehaviorCategory.REFACTOR: {"regression", "characterization"},
    BehaviorCategory.UNKNOWN: {"review", "behavior"},
}


@dataclass(frozen=True)
class IndexedTest:
    path: str
    symbol: str
    imports: frozenset[str]
    name_tokens: frozenset[str]
    body_tokens: frozenset[str]


@dataclass
class TestIndex:
    __test__: ClassVar[bool] = False
    tests: list[IndexedTest]
    incomplete: bool
    warnings: list[str]


class _ImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.update(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.add(node.module)
            self.imports.update(f"{node.module}.{alias.name}" for alias in node.names)


def _is_test_path(path: str, roots: list[str]) -> bool:
    pure = PurePosixPath(path)
    root_match = any(
        pure == PurePosixPath(root) or PurePosixPath(root) in pure.parents for root in roots
    )
    convention = pure.name.startswith("test_") or pure.name.endswith("_test.py")
    return path.endswith(".py") and (root_match or convention)


def _tokens(text: str) -> frozenset[str]:
    tokens: set[str] = set()
    for item in TOKEN_RE.findall(text):
        lowered = item.casefold()
        tokens.add(lowered)
        tokens.update(part for part in lowered.split("_") if part)
    return frozenset(tokens)


def _index_source(path: str, source: str) -> list[IndexedTest]:
    tree = ast.parse(source, type_comments=True)
    imports_visitor = _ImportVisitor()
    imports_visitor.visit(tree)
    imports = frozenset(item.casefold() for item in imports_visitor.imports)
    result: list[IndexedTest] = []

    def walk(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                walk(node.body, f"{prefix}{node.name}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test"):
                    body_text = redact_text(ast.unparse(node), max_chars=4000)
                    result.append(
                        IndexedTest(
                            path=path,
                            symbol=f"{prefix}{node.name}",
                            imports=imports,
                            name_tokens=_tokens(node.name),
                            body_tokens=_tokens(body_text),
                        )
                    )

    walk(tree.body)
    return result


def build_test_index(repo: GitRepository, head_commit: str, config: WeaverConfig) -> TestIndex:
    tests: list[IndexedTest] = []
    incomplete = False
    warnings: list[str] = []
    for path in repo.list_files(head_commit):
        if exclusion_reason(path) or not _is_test_path(path, config.paths.test_roots):
            continue
        source = repo.read_blob(head_commit, path, config.rules.max_file_bytes)
        if source is None:
            incomplete = True
            warnings.append("At least one candidate test file was oversized, binary, or non-UTF-8.")
            continue
        try:
            tests.extend(_index_source(path, source))
        except (SyntaxError, ValueError, TypeError):
            incomplete = True
            warnings.append(f"Could not parse candidate test file {path!r}; mapping is incomplete.")
    tests.sort(key=lambda item: (item.path, item.symbol))
    return TestIndex(tests=tests, incomplete=incomplete, warnings=sorted(set(warnings)))


def _module_name(path: str) -> str:
    pure = PurePosixPath(path)
    parts = list(pure.with_suffix("").parts)
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]
    return ".".join(parts)


def _mirrored(source_path: str, test_path: str) -> bool:
    source = PurePosixPath(source_path)
    test = PurePosixPath(test_path)
    source_stem = source.stem
    test_stem = test.stem.removeprefix("test_").removesuffix("_test")
    if source_stem != test_stem:
        return False
    source_parts = [item for item in source.parent.parts if item not in {"src", "lib"}]
    test_parts = [item for item in test.parent.parts if item not in {"tests", "test"}]
    return not source_parts or not test_parts or source_parts[-2:] == test_parts[-2:]


def map_candidate_tests(
    candidates: list[SemanticCandidate],
    index: TestIndex,
    config: WeaverConfig,
) -> dict[int, list[CandidateTest]]:
    """Return capped static candidates; terminology alone can never create a match."""
    result: dict[int, list[CandidateTest]] = {}
    for candidate_index, candidate in enumerate(candidates):
        symbol_token = candidate.symbol.rsplit(".", 1)[-1].casefold()
        module = _module_name(candidate.path).casefold()
        ranked: list[CandidateTest] = []
        for test in index.tests:
            score = 0.0
            reasons: list[str] = []
            structural = False
            if any(
                glob_matches(candidate.path, mapping.source)
                and any(glob_matches(test.path, pattern) for pattern in mapping.tests)
                for mapping in config.mapping
            ):
                score += 0.30
                reasons.append("explicit configured mapping")
                structural = True
            if _mirrored(candidate.path, test.path):
                score += 0.25
                reasons.append("mirrored source/test path")
                structural = True
            if any(
                imported == module
                or imported.startswith(f"{module}.")
                or module.startswith(f"{imported}.")
                or imported.endswith(f".{module}")
                or imported.endswith(f".{symbol_token}")
                for imported in test.imports
            ):
                score += 0.25
                reasons.append("direct module or symbol import")
                structural = True
            if symbol_token and symbol_token in test.name_tokens:
                score += 0.20
                reasons.append("changed symbol token in test name")
                structural = True
            if symbol_token and symbol_token in test.body_tokens:
                score += 0.10
                reasons.append("changed symbol token in bounded test body")
                structural = True
            if CATEGORY_TERMS[candidate.category] & (test.name_tokens | test.body_tokens):
                score += 0.10
                reasons.append("behavior-category terminology")
            score = min(1.0, score)
            if structural and score >= 0.35:
                ranked.append(
                    CandidateTest(
                        path=test.path,
                        symbol=test.symbol,
                        match_score=round(score, 2),
                        match_reasons=reasons,
                    )
                )
        ranked.sort(key=lambda item: (-item.match_score, item.path, item.symbol))
        result[candidate_index] = ranked[: config.rules.max_candidate_tests_per_obligation]
    return result
