# Evaluation

The MVP evaluation corpus is repository-local, deterministic, and derived from the supported
taxonomy. Fixtures cover boundary/default/error/retry/authorization/output/state/dependency/
side-effect/ordering changes, a return-annotation signature change, stable refactors, ambiguous
syntax, a function move between files that both remain, no-Python changes, parse failure, and bounded
oversized input.

Metrics are calculated from machine-readable expected categories and evidence anchors:

- material finding precision;
- supported-pattern recall;
- evidence correctness and fabricated evidence count;
- required obligation-concept match;
- candidate-coverage wording;
- deterministic preprocessing latency;
- structured call count and input size.

Each case also has a complete canonical JSON golden with analysis IDs and repository refs/commits
normalized. Contract changes must update these goldens intentionally and record the reason in
`docs/decisions.md`.

Release thresholds are at least 80% material precision, at least 70% supported-pattern recall, zero
fabricated evidence references, an obligation for every high/critical behavior, and no candidate
described as verified coverage. The corpus is intentionally small and synthetic; it does not validate
dynamic behavior or external business contracts.

## Local MVP result (2026-07-19)

On CPython 3.12.3 / Linux with Git 2.43.0, the 17-case corpus (eleven material signature/taxonomy
patterns plus refactor, ambiguity, cross-file move, no-Python, mixed-parse, and
critical-prioritization cases) produced
100% material precision, 100% supported-pattern recall, 100% evidence-anchor correctness, 100%
required obligation-concept match, and zero fabricated evidence references. Every high/critical
finding had a linked obligation, and every candidate test remained explicitly unverified.

The deterministic performance suite covers both a 100-symbol AST fixture and a warmed full-service
fixture with 40 files, 3,000 changed lines, and 100 symbols, each with the plan's five-second ceiling.
They completed in approximately 0.012 seconds and 0.389 seconds respectively in the final
local timing run. The complete automated suite reports 93.14% overall branch-aware coverage, with at
least 90% branch coverage in each critical boundary/transport module. No live LLM call or credential
was used.

The fixture-label review removed a state-transition expectation from the retry-predicate case because
the assignment itself was unchanged; retaining it would have rewarded a false positive. These numbers
describe only the bounded synthetic corpus and are not a claim about arbitrary repositories.
