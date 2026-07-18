# Evaluation

The MVP evaluation corpus is repository-local, deterministic, and derived from the supported
taxonomy. Fixtures cover boundary/default/error/retry/authorization/output/state/dependency/
side-effect/ordering changes, stable refactors, ambiguous syntax, renames, no-Python changes, parse
failure, and bounded oversized input.

Metrics are calculated from machine-readable expected categories and evidence anchors:

- material finding precision;
- supported-pattern recall;
- evidence correctness and fabricated evidence count;
- required obligation-concept match;
- candidate-coverage wording;
- deterministic preprocessing latency;
- structured call count and input size.

Release thresholds are at least 80% material precision, at least 70% supported-pattern recall, zero
fabricated evidence references, an obligation for every high/critical behavior, and no candidate
described as verified coverage. The corpus is intentionally small and synthetic; it does not validate
dynamic behavior or external business contracts.

## Local MVP result (2026-07-17)

On CPython 3.12.13 / Windows, the ten specification-derived material cases produced 100% material
precision, 100% supported-pattern recall, and zero fabricated evidence references. All emitted
findings carried deterministic evidence. The 100-symbol reference preprocessing fixture completed in
approximately 0.01 seconds in the pytest timing run, below the five-second target. No live LLM call or
credential was used.

The fixture-label review removed a state-transition expectation from the retry-predicate case because
the assignment itself was unchanged; retaining it would have rewarded a false positive. These numbers
describe only the bounded synthetic corpus and are not a claim about arbitrary repositories.
