# Architecture

The plugin follows a typed, bounded pipeline:

```text
request/config -> repository + resolved refs -> changed committed blobs -> AST deltas
-> deterministic evidence/candidates -> static candidate-test index -> optional structured LLM
-> reconciliation -> risk/confidence -> obligations -> canonical JSON -> optional Markdown
```

`plugin.py` is the only Hermes adapter. Registration closes over `ctx.llm` but performs no Git or LLM
work. `service.py` orchestrates modules without importing Hermes internals. `git_diff.py` is the sole
subprocess boundary and invokes only Git with argument arrays, resolved commit IDs, timeouts, bounded
captured output, disabled external diff/text conversion, and `shell=False`.

`ast_diff.py` parses text with the Python AST without importing target modules. Deterministic rules
create evidence before model use. `semantic_interpreter.py` sends bounded, delimited evidence through
`ctx.llm.complete_structured`, locally validates output, rejects fabricated evidence IDs, and cannot
initiate actions. Evidence is batched by module, prioritized by configured critical paths, bounded per
symbol and per call, and retried once only for schema-invalid responses within the eight-call ceiling.
A bounded, redacted committed README excerpt may provide repository purpose context. `test_mapper.py`
parses committed tests statically and always labels matches as unverified candidates.

When global file or line limits are exceeded, explicitly configured critical paths are analyzed first
and every omitted count/reason is carried into canonical scope and Markdown. Parse-incomplete files
produce bounded unknown findings rather than losing all evidence. Conservative symbol matching can
connect renamed or moved functions, but refuses ambiguous near-ties.

The canonical schema version is `1.0`. Markdown is derived entirely from the canonical analysis.
Risk estimates impact and test gap; confidence estimates support strength. They are intentionally
independent.
