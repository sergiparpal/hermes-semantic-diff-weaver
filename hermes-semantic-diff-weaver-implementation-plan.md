# Hermes Semantic Diff Weaver: Codex Implementation Plan

> Plan version: 1.0  
> Target release: MVP v0.1  
> Prepared: 2026-07-17  
> Source specification: `hermes-semantic-diff-weaver-spec.md`, Draft v0.1

## 1. Plan Status and Intended Outcome

This document is the implementation plan for the MVP defined in `hermes-semantic-diff-weaver-spec.md`. It is written for an autonomous programming agent such as Codex and is intended to be executable from an initially empty repository without requiring human approval or verification between implementation stages.

The completed MVP will be a read-only Hermes Agent plugin that:

- registers one Hermes tool named `analyze_semantic_diff`;
- analyzes a bounded Git diff between a base revision and a head revision;
- supports Python source and common pytest/unittest test layouts;
- extracts structural changes without importing or executing repository code;
- converts deterministic evidence and bounded LLM interpretation into traceable behavioral findings;
- produces risk-ranked test obligations;
- maps findings to candidate existing tests without claiming runtime coverage;
- returns schema-versioned JSON and an optional pull-request-ready Markdown brief;
- degrades to a deterministic structural report when the Hermes-hosted LLM is unavailable;
- enforces repository boundaries, secret exclusions, size limits, and prompt-injection defenses.

The implementation is complete only when every MVP acceptance criterion in Section 17 of this plan passes automatically.

## 2. Scope Boundaries

### 2.1 In scope for the MVP

- Local Git repositories.
- A base Git ref and an optional head Git ref, defaulting to `HEAD`.
- Committed content addressable by the two resolved refs.
- Python source files.
- Static source and test inspection.
- Python AST comparison.
- Deterministic detection of supported semantic patterns.
- Bounded structured LLM inference through Hermes Agent's host-owned model.
- Candidate test discovery and ranking.
- Risk, confidence, and obligation-priority scoring.
- JSON and Markdown rendering.
- Directory-plugin installation and pip entry-point packaging.
- Automated unit, golden, contract, integration, security, and performance tests.

### 2.2 Explicitly out of scope

- Reading uncommitted working-tree or staged changes as a separate diff mode.
- Fetching pull requests or refs from a network host.
- Executing tests in the analyzed target repository.
- Importing any module from the analyzed target repository.
- Running target-repository hooks, package managers, build tools, or generators.
- Writing source code or tests into the analyzed target repository.
- Dynamic coverage, mutation testing, production telemetry, or historical test data.
- Verified source-to-test coverage claims.
- Languages other than Python.
- Merge blocking or policy enforcement.
- Test-file generation.
- GitHub, GitLab, or Bitbucket API integration.
- Cross-repository history.

### 2.3 Product wording constraints

The implementation and documentation must consistently use the following language:

- Existing tests are **candidate tests**, never verified coverage.
- Behavioral conclusions are **inferred** or **appear to have changed**, unless a deterministic fact is being described.
- Risk and confidence are separate values.
- A high-risk, low-confidence item is a review question, not a factual assertion.
- The plugin is advisory, read-only, and local by default.

## 3. Fixed Design Decisions

The specification contains open questions. The following decisions remove ambiguity so Codex can implement without waiting for a human design review.

| Topic | MVP decision | Reason |
|---|---|---|
| Repository purpose | Read at most a bounded README excerpt when available; otherwise analyze without a project summary. Do not require user input. | Keeps setup zero-configuration while bounding model input. |
| LLM batching | Group related changed symbols by module and shared evidence, subject to per-batch character and symbol limits. Do not use one call per symbol or blindly one call per file. | Preserves cross-symbol context while enforcing the eight-call ceiling. |
| Configuration | All repository configuration is optional. Built-in conservative defaults must produce a useful analysis. | Avoids a configuration gate before first use. |
| Low-confidence findings | Emit findings at or above the configured minimum confidence. Render high-risk findings below `0.60` as review questions. Move findings below the minimum into warnings/limitations rather than presenting them as facts. | Preserves uncertainty without flooding the report. |
| Rename and move matching | Match exact qualified names first, then use file rename metadata, signature similarity, normalized AST fingerprints, and body-token similarity. Require a conservative threshold and report ambiguity. | Supports common refactors without overclaiming. |
| Evaluation corpus | Start with repository-local, specification-derived fixtures and machine-readable labels. Add public-repository cases only after the local corpus passes. | Makes the MVP reproducible and offline-testable. |
| LLM outage | Return a reduced deterministic report by default, including structural candidates, evidence, warnings, and conservative obligations where templates are safe. | Ensures graceful degradation. |
| Refactor threshold | Classify as `refactor_likely_no_behavior_change` only when normalized behavior-bearing structures are unchanged and the materiality score is below the configured threshold. Otherwise use the strongest supported category or `unknown_semantic_change`. | Optimizes for precision and explicit uncertainty. |
| Output transport | The handler always returns a JSON-encoded string, as required by Hermes. `json` returns the canonical analysis object, `markdown` returns a small JSON envelope containing the Markdown string and identity fields, and `both` returns an envelope containing both artifacts. | Preserves a stable machine interface and Hermes tool-handler compatibility. |
| LLM model selection | Use the user's active Hermes provider, model, agent, and auth profile. Do not request overrides in the MVP. | Avoids Hermes trust-gate configuration and extra credentials. |
| Plugin surface | Register one standalone/general tool. Do not register hooks, slash commands, CLI commands, skills, or tool overrides. | Matches the product scope and minimizes privilege. |

If later evidence shows that a fixed decision conflicts with the installed Hermes API, Codex may make the smallest compatibility adjustment, record it in `docs/decisions.md`, add a regression test, and continue.

## 4. Autonomous Codex Execution Protocol

### 4.1 General operating rules

Codex must execute the stages in dependency order, but it may combine adjacent stages when doing so reduces rework. It must:

1. Inspect the current repository and preserve unrelated user changes.
2. Maintain a short implementation checklist derived from Section 16.
3. Implement a vertical slice early, then expand the supported taxonomy.
4. Run the automated gate for every stage before marking that stage complete.
5. Fix gate failures before proceeding when they were introduced by the current work.
6. Record assumptions and compatibility deviations in repository documentation.
7. Prefer deterministic tests with fake LLM responses over live paid-model tests.
8. Continue through all stages without asking for routine human confirmation.
9. Avoid commits, pushes, releases, or publication unless separately authorized.
10. Never weaken a security invariant merely to make a test pass.

### 4.2 Non-blocking decision policy

Codex should use the defaults in this plan whenever information is absent. A question to the user is justified only if all of the following are true:

- the answer cannot be discovered from repository files, installed tooling, or official Hermes documentation;
- different answers would materially change the public contract, licensing, or safety posture;
- choosing a default would create meaningful rework or risk.

If a question is helpful but not essential, Codex should ask it in Codex while continuing all unaffected work. Examples include the desired author string in `plugin.yaml`, the eventual package publisher, and whether to add a public evaluation repository. Use these defaults if no answer is available:

- author: `Hermes Semantic Diff Weaver contributors`;
- license: do not invent one; add a release-blocking note while continuing implementation and tests;
- distribution: build local wheel and source archive, but do not publish;
- public corpus: defer; use local fixtures;
- Hermes version: test the installed version and the current documented plugin contract; record the tested version.

### 4.3 Legitimate pause conditions

Implementation may pause only when:

- a required destructive action is outside the user's request;
- a credential or paid external service is required and no deterministic substitute exists;
- the installed Hermes runtime lacks the documented plugin interfaces and a compatible runtime cannot be obtained safely;
- the repository contains conflicting user changes in the exact files Codex must replace and those changes cannot be preserved;
- a licensing decision is required for publication, not merely local development.

None of these conditions should interrupt work on independent modules or tests.

## 5. Hermes Agent Plugin Requirements

This section is normative for implementation. It captures the current Hermes general-plugin contract that this project must satisfy.

### 5.1 Runtime compatibility

- Use Python `>=3.11`, matching the current Hermes Agent runtime floor.
- Use a Git CLI available on `PATH`; verify it during analysis and return a structured error if missing or unusable.
- Do not import Hermes internals from analysis modules. Limit Hermes coupling to the registration adapter and the `ctx.llm` facade.
- At the beginning of implementation, record the installed Hermes version and inspect the signatures of `PluginContext.register_tool` and `PluginLlm.complete_structured` when available.
- Before release, determine and document the lowest Hermes release that passes the plugin contract tests. Do not guess a minimum version in package metadata.

### 5.2 Directory-plugin structure

Hermes discovers a directory plugin only when the plugin directory contains both:

- `plugin.yaml`;
- `__init__.py` exporting `register(ctx)`.

Use this manifest:

```yaml
name: hermes-semantic-diff-weaver
kind: standalone
version: 0.1.0
description: Analyze Git diffs and produce evidence-backed, risk-ranked test obligations.
author: Hermes Semantic Diff Weaver contributors
provides_tools:
  - analyze_semantic_diff
```

`kind: standalone` is the current Hermes manifest term for a general plugin that registers its own tool. No `requires_env` entry is needed because the MVP uses the user's active Hermes model and has no plugin-specific credentials.

### 5.3 Registration contract

The repository-root `__init__.py` must expose `register(ctx)` and delegate to the package implementation. Registration must occur once at Hermes startup and must not perform Git analysis or an LLM call.

The effective registration must be equivalent to:

```python
def register(ctx):
    def handler(args, **kwargs):
        return handle_analyze_semantic_diff(args, llm=ctx.llm, **kwargs)

    ctx.register_tool(
        name="analyze_semantic_diff",
        toolset="semantic_diff_weaver",
        schema=ANALYZE_SEMANTIC_DIFF_SCHEMA,
        handler=handler,
        description=(
            "Analyze the behavioral meaning of a Git diff and return "
            "evidence-backed, risk-ranked test obligations."
        ),
        override=False,
    )
```

Required details:

- The tool schema must include `name`, a precise `description`, and JSON Schema `parameters`.
- The schema description must state when the model should call the tool and that it does not execute or modify code.
- The handler signature must accept one argument dictionary plus `**kwargs` because Hermes may pass runtime context.
- The handler must catch expected failures and return a JSON-encoded error object rather than raising into the Hermes tool loop.
- Every handler return value must be a string containing valid JSON, including Markdown-only mode.
- Do not set `override=True` and do not shadow a built-in tool.
- Do not reach into the global Hermes tool registry or agent internals.

### 5.4 Hermes-hosted structured LLM contract

Use `ctx.llm.complete_structured(...)` only inside the tool handler's analysis flow. The call must use:

- `instructions`: the trusted inference instructions;
- `input`: one or more typed text blocks containing bounded, explicitly delimited untrusted evidence;
- `json_schema`: the inference response schema;
- `schema_name`: a stable name such as `semantic_diff_batch_v1`;
- low temperature;
- bounded `max_tokens` and `timeout`;
- a stable `purpose`, such as `semantic-diff-interpretation`.

Do not pass `provider`, `model`, `agent_id`, or `profile` in the MVP. Hermes permits request-shaping fields by default but applies a fail-closed trust gate to provider, model, agent, and auth-profile overrides.

Treat the result as follows:

- Accept `result.parsed` only when `result.content_type == "json"` and local model validation succeeds.
- Treat text-mode results, empty parsed values, schema validation failures, trust errors, timeouts, provider failures, and unexpected exceptions as bounded LLM failures.
- Retry at most once, only for an explicitly retryable schema/transport failure and only if the total LLM call budget remains available.
- Never let an LLM failure discard deterministic findings.
- Capture aggregate token and cost information only when returned, never credentials or raw provider responses.

### 5.5 Discovery, enablement, and installation

Support all relevant Hermes discovery paths in documentation and automated smoke tests:

- User plugin: `~/.hermes/plugins/hermes-semantic-diff-weaver/`.
- Project plugin: `./.hermes/plugins/hermes-semantic-diff-weaver/`; project plugins require explicit trust through `HERMES_ENABLE_PROJECT_PLUGINS=true`.
- Pip plugin: expose the `hermes_agent.plugins` entry-point group.

Plugins are opt-in. Installation instructions must include:

```text
hermes plugins enable hermes-semantic-diff-weaver
hermes plugins list
```

Debugging documentation must mention `HERMES_PLUGINS_DEBUG=1` and Hermes' plugin logs. Tests must use a temporary Hermes home and must not modify the user's real Hermes configuration.

### 5.6 Pip entry point

The package metadata must include:

```toml
[project.entry-points."hermes_agent.plugins"]
hermes-semantic-diff-weaver = "hermes_semantic_diff_weaver.plugin"
```

The target module must export `register(ctx)`. Directory installation remains the simplest development path; a wheel-install discovery test is required before the packaging stage is complete.

## 6. Repository and Package Layout

Implement the following layout. The small repository-root shim preserves Hermes directory-plugin compatibility, while the importable package supports clean testing and pip entry points.

```text
hermes-semantic-diff-weaver/
├── plugin.yaml
├── __init__.py
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── hermes-semantic-diff-weaver-spec.md
├── hermes-semantic-diff-weaver-implementation-plan.md
├── docs/
│   ├── architecture.md
│   ├── configuration.md
│   ├── security.md
│   ├── evaluation.md
│   └── decisions.md
├── hermes_semantic_diff_weaver/
│   ├── __init__.py
│   ├── plugin.py
│   ├── schemas.py
│   ├── models.py
│   ├── errors.py
│   ├── config.py
│   ├── path_policy.py
│   ├── git_diff.py
│   ├── ast_diff.py
│   ├── semantic_candidates.py
│   ├── semantic_interpreter.py
│   ├── obligations.py
│   ├── test_mapper.py
│   ├── scoring.py
│   ├── renderer.py
│   └── service.py
└── tests/
    ├── conftest.py
    ├── unit/
    ├── contract/
    ├── integration/
    ├── security/
    ├── performance/
    ├── evaluation/
    └── fixtures/
        ├── repositories/
        ├── llm_responses/
        └── golden/
```

Module boundaries are mandatory:

| Module | Responsibility | Must not do |
|---|---|---|
| `plugin.py` | Hermes registration and transport adapter | Analyze a repository during registration |
| `schemas.py` | Hermes input schema and LLM response schema | Execute logic |
| `models.py` | Validated domain and output models | Call Git or the LLM |
| `errors.py` | Stable error codes and safe error conversion | Include raw secret/source payloads |
| `config.py` | Safe YAML loading, defaults, precedence, validation | Execute YAML tags or repository code |
| `path_policy.py` | Repository containment, file policy, glob validation | Follow arbitrary paths outside policy |
| `git_diff.py` | Ref resolution, changed-file metadata, hunks, blob reads | Use a shell or run Git hooks |
| `ast_diff.py` | Parse old/new text and compute structural deltas | Import analyzed modules |
| `semantic_candidates.py` | Deterministic pattern detection and evidence records | Invent business behavior |
| `semantic_interpreter.py` | Bounded `ctx.llm` calls and result validation | Read files or execute tools based on model output |
| `obligations.py` | Deterministic templates, merge, deduplication, caps | Claim candidate tests prove coverage |
| `test_mapper.py` | Static candidate test indexing and ranking | Execute target tests |
| `scoring.py` | Risk, confidence, priority, labels | Hide score components |
| `renderer.py` | Stable JSON-mode transport and Markdown output | Recompute analysis |
| `service.py` | Orchestrate the bounded pipeline | Contain Hermes-specific global imports |

## 7. Dependency and Tooling Policy

### 7.1 Runtime dependencies

Keep runtime dependencies minimal:

- Python standard library for Git subprocesses, AST processing, paths, hashing, JSON, and concurrency primitives.
- Pydantic 2 for domain validation and JSON Schema generation.
- PyYAML 6 for repository configuration, always using `safe_load`.

Do not add GitPython, tree-sitter, an embedding database, an HTTP client, a tokenizer package, or an LLM SDK for the MVP. Hermes owns the LLM client. Every added dependency must have a justified lower and upper bound, and the lock file must pin exact development resolutions.

### 7.2 Development dependencies

Use:

- `pytest`;
- `pytest-cov`;
- `pytest-timeout`;
- `ruff`;
- `build`;
- an exact lock file generated by the chosen environment manager.

Static type checking may be added if it can run reliably in the target environment, but it must not delay the vertical slice. Ruff must at least enforce explicit text encodings, unused imports, obvious correctness errors, and consistent formatting.

### 7.3 Standard commands

Define these commands in the README and use them in stage gates:

```text
python -m pytest
python -m pytest tests/unit tests/contract
python -m pytest tests/integration
python -m pytest tests/security
python -m pytest tests/evaluation
python -m ruff check .
python -m ruff format --check .
python -m build
```

Tests must run on Windows, Linux, and macOS. Do not depend on POSIX-only process, path, signal, or file-mode behavior.

## 8. Public Contracts

### 8.1 Tool input schema

Implement the specification's input schema with these precise semantics:

| Field | Required | Default | Validation and behavior |
|---|---:|---|---|
| `repo_path` | Yes | None | Non-empty local path. Resolve it and obtain the Git top level. The resolved input must equal or be contained by that top level. |
| `base_ref` | Yes | None | Non-empty ref resolved to a commit before any diff command. Reject option-like refs and invalid revisions safely. |
| `head_ref` | No | `HEAD` | Same resolution rules as `base_ref`. |
| `risk_profile` | No | None | Explicit YAML config path. Accept only a bounded regular file with `.yaml` or `.yml`; validate it with the same schema as repository config. |
| `include` | No | Config/default | List of repository-relative glob patterns. Reject absolute paths, NULs, and parent traversal. |
| `exclude` | No | Config/default | Same constraints as `include`; merged with non-disableable secret and control-directory exclusions. |
| `output_format` | No | `both` | One of `json`, `markdown`, or `both`. |

Do not add undocumented required inputs. Unknown fields should be rejected at the transport-model boundary to expose caller mistakes.

### 8.2 Canonical analysis model

The canonical JSON analysis uses `schema_version: "1.0"` and contains:

- `analysis_id` with an opaque `sdw_` prefix;
- repository identity and resolved commit hashes;
- summary counts, overall risk, numeric risk score, and overall confidence;
- changed-scope metadata, including omitted scope;
- `behavior_changes`;
- `test_obligations`;
- warnings;
- limitations;
- LLM status and aggregate usage when available;
- deterministic-mode indicator.

Use strict validated models. Additive fields are permitted within schema version 1 only when old consumers can ignore them. Renames, removals, semantic changes, or type changes require a schema version change.

### 8.3 Behavior change model

Every behavior change must contain:

- stable per-analysis ID such as `bc-001`;
- one category from the exact taxonomy in the specification;
- concise summary;
- observable impact;
- `risk` label and `risk_score` from 0 to 100;
- `confidence` from 0.0 to 1.0;
- one or more evidence records for every material or high-priority finding;
- assumptions, possibly empty;
- `presentation`: `finding` or `review_question`;
- origin: `deterministic`, `llm_supported`, or `deterministic_fallback`.

Unknown taxonomy values are invalid. Evidence references must resolve to pre-existing evidence IDs created by deterministic preprocessing; the model may never create a path or line reference directly.

### 8.4 Evidence model

Every evidence record must include:

- deterministic evidence ID;
- repository-relative POSIX-style path;
- qualified symbol when available;
- old and new line ranges when available;
- hunk identity;
- compact old/new expression or structural summary;
- evidence kind;
- parser completeness flag.

Evidence text must be bounded and may not include an entire source file. Normalize paths to `/` in output on every operating system.

### 8.5 Test obligation model

Every obligation must include:

- stable per-analysis ID such as `to-001`;
- one or more linked behavior-change IDs;
- type: positive, negative, boundary, error, state, interaction, regression, or review;
- integer priority from 0 to 100;
- concise title;
- `given`, `when`, and `then` fields phrased as observable behavior;
- zero or more candidate existing tests;
- coverage status: `candidate_exists_unverified`, `no_candidate_found`, or `mapping_incomplete`;
- origin and confidence.

Reject obligations that reference unknown behavior IDs or test paths outside the repository.

### 8.6 Transport shapes

The tool handler must return one of these JSON-encoded shapes:

- `json`: the canonical analysis object.
- `markdown`: `{ "success": true, "schema_version": "1.0", "analysis_id": "...", "markdown": "..." }`.
- `both`: `{ "success": true, "schema_version": "1.0", "analysis": { ... }, "markdown": "..." }`.
- failure for any mode: the error model in Section 8.7.

The canonical analysis should include `success: true` so success and failure are distinguishable without inference. Keep the Markdown renderer derivable entirely from the canonical object.

### 8.7 Error contract

All expected failures return:

```json
{
  "success": false,
  "error": "diff_too_large",
  "message": "The diff contains 5842 changed lines; the configured limit is 3000.",
  "remediation": "Narrow the include patterns, split the change, or increase rules.max_diff_lines."
}
```

Implement these exact public error codes:

- `not_a_git_repository`;
- `invalid_ref`;
- `path_outside_repository`;
- `unsupported_language`;
- `diff_too_large`;
- `parse_failure`;
- `llm_unavailable`;
- `llm_schema_failure`;
- `configuration_error`;
- `internal_error`.

Also define internal typed exceptions as needed, but map them to the public codes. Messages may contain safe counts and normalized relative paths but must not contain source bodies, environment values, credentials, subprocess environment dumps, or raw model responses.

Return `unsupported_language` only when configuration or an explicit request selects a language other than Python. A valid diff with no changed Python source is a successful empty analysis with a limitation, not an error. Return `llm_unavailable` only when deterministic fallback is disabled or no meaningful deterministic result can be produced; otherwise return a successful reduced report with an explicit LLM warning.

## 9. Configuration Contract

### 9.1 Precedence

Use this precedence, from highest to lowest:

1. Tool arguments.
2. Explicit `risk_profile` file.
3. Repository `.hermes/semantic-diff-weaver.yaml`.
4. Repository `.semantic-diff-weaver.yaml`.
5. Built-in defaults.

If both repository files exist, use the `.hermes` file and emit a warning that the lower-priority file was ignored. Lists replace lower-priority lists unless the field is explicitly documented as additive. Mandatory secret exclusions are always additive and cannot be disabled.

### 9.2 Default configuration

Use these MVP defaults:

```yaml
version: 1

language:
  primary: python

paths:
  include:
    - "**/*.py"
  exclude:
    - "**/migrations/**"
    - "**/generated/**"
    - "**/vendor/**"
  test_roots:
    - "tests"

critical_paths: []

rules:
  max_changed_files: 40
  max_diff_lines: 3000
  max_changed_symbols: 100
  max_file_bytes: 1000000
  max_readme_chars: 4000
  max_evidence_chars_per_symbol: 6000
  max_model_input_chars_per_call: 48000
  max_llm_calls: 8
  max_obligations_per_behavior: 6
  max_test_obligations: 100
  max_candidate_tests_per_obligation: 5
  minimum_report_confidence: 0.45
  review_question_confidence: 0.60
  refactor_materiality_threshold: 0.25
  emit_low_risk_refactors: false
  deterministic_fallback: true

mapping: []

privacy:
  redact_patterns: true
  allow_network: false
```

### 9.3 Validation

- Use `yaml.safe_load` and reject non-mapping roots, duplicate semantic mappings, unknown top-level sections, invalid types, negative limits, invalid ranges, and unsupported `version` values.
- Bound config size before parsing.
- Reject custom YAML tags.
- Normalize glob separators to `/`.
- Reject absolute include/exclude/test-root/mapping paths and parent traversal.
- Permit an explicitly supplied `risk_profile` outside the repository only because the caller named it directly; resolve it, bound it, require a regular YAML file, and never follow paths named from inside that file.
- Repository configuration is untrusted data and may not alter network, execution, secret-exclusion, or repository-boundary invariants.

## 10. Analysis Pipeline and Algorithms

### 10.1 Pipeline sequence

```text
Validate request and load configuration
    -> resolve repository and Git refs
    -> collect bounded changed-file and hunk metadata
    -> read old/new Python blobs without checkout
    -> extract and match AST symbols
    -> create deterministic structural deltas and evidence records
    -> detect semantic candidates
    -> index and rank candidate tests
    -> batch bounded evidence for structured LLM interpretation
    -> validate and reconcile LLM output with deterministic evidence
    -> generate, merge, and deduplicate test obligations
    -> calculate risk, confidence, and priority
    -> enforce global caps and record omitted scope
    -> render canonical JSON and optional Markdown
```

Every stage consumes and returns typed models. No stage may silently discard errors, omitted scope, or truncation.

### 10.2 Repository and Git safety

Use `subprocess.run` with an argument list, `shell=False`, a fixed timeout, captured text output with an explicit encoding/error policy, and `cwd` set to the resolved repository root. Do not interpolate arguments into a shell command.

Required procedure:

1. Resolve `repo_path` with `Path.resolve(strict=True)`.
2. Run `git rev-parse --show-toplevel` and resolve the returned path.
3. Verify the input path is the root or a descendant of that root.
4. Resolve base and head refs to full commit hashes before using them in later commands.
5. Use resolved hashes, not raw refs, in diff and blob commands.
6. Disable external diff drivers and avoid Git hooks.
7. Collect rename/copy metadata with `git diff --name-status -M -C`.
8. Collect counts before source bodies. Enforce file and changed-line limits early.
9. Add `--` before pathspec arguments.
10. Read committed blobs with `git show <commit>:<validated-repository-relative-path>` or an equivalent plumbing command; never checkout either revision.

Use NUL-delimited (`-z`) output for every Git command that returns path lists, including name/status and numstat output, so spaces, tabs, newlines, Unicode, and shell metacharacters in valid filenames cannot corrupt parsing. Disable external diff and text-conversion drivers with `--no-ext-diff` and `--no-textconv` wherever those mechanisms could apply.

Validate every Git-reported path before reading it. Reject NULs, absolute paths, drive-relative paths, parent traversal, control-directory paths such as `.git`, and resolved escapes. Symlink entries must be treated as metadata and must not be followed outside the repository.

### 10.3 Changed-file filtering

Apply filters in this order:

1. Git reports the changed paths and status.
2. Normalize paths to repository-relative POSIX format.
3. Apply non-disableable security exclusions.
4. Apply caller/config include rules.
5. Apply caller/config exclude rules.
6. Restrict semantic analysis to `.py` source files.
7. Identify tests separately using configured roots and filename conventions.

Mandatory exclusions include, at minimum:

- `.git/**` and other VCS control directories;
- `.env`, `.env.*`, and common credential file names;
- private keys, certificates, keystores, and SSH material;
- package caches and virtual environments;
- generated/vendor paths unless the caller explicitly includes them and they are not secret/control paths;
- binary and oversized files.

Report excluded and omitted counts by reason without echoing sensitive names when the name itself may reveal a secret.

### 10.4 AST symbol extraction

For each old and new Python blob:

- parse with `ast.parse` without importing the module;
- record module, class, function, async function, and method symbols;
- build qualified names from lexical nesting;
- record decorators by safe name only;
- record argument names, kinds, annotations as normalized syntax, and defaults;
- record returns, raises, calls, comparisons, Boolean conditions, assignments, loops, literals, and context-manager usage;
- record start/end line ranges using AST coordinates;
- remove location attributes and non-behavioral formatting from structural fingerprints;
- ignore a leading docstring when calculating a behavior-bearing body fingerprint, while retaining a bounded docstring excerpt as optional context;
- create compact, bounded structural summaries instead of retaining unlimited source.

If one file fails to parse, retain its diff evidence, emit a parse warning, lower confidence, and continue with other files. Return top-level `parse_failure` only when no supported changed source can be analyzed and no meaningful deterministic report can be produced.

### 10.5 Symbol matching

Match old and new symbols in passes:

1. Same normalized path and exact qualified name.
2. Git-renamed path and exact qualified name.
3. Same parent scope and compatible signature with a normalized body fingerprint match.
4. Conservative similarity match using signature shape, calls, control-flow inventory, and normalized AST tokens.
5. Otherwise classify as added or removed.

Never force a one-to-one rename match when multiple candidates have near-equal scores. Record ambiguous candidates and lower confidence. Unit-test nested functions, methods, async functions, overload-like definitions, moved files, and duplicate names.

### 10.6 Structural delta extraction

For each matched or added/removed symbol, calculate:

- signature changes, including parameter kind, name, default, and annotation;
- comparison/operator changes;
- condition additions, removals, inversions, and reordered Boolean terms;
- literal and threshold changes;
- exception additions, removals, type changes, swallowing, wrapping, and propagation changes visible in syntax;
- return additions, removals, and visible shape/type changes;
- call additions/removals and ordering changes;
- assignment target/value changes;
- retry, timeout, loop bound, and stop-condition changes;
- likely authorization/validation guard changes using configurable names and call structure;
- side-effect call changes using conservative call-name and context signals;
- structural-only changes where behavior-bearing fingerprints remain stable.

Intersect AST line ranges with diff hunks so unchanged surrounding symbols do not become findings merely because their files changed.

### 10.7 Deterministic semantic candidate rules

Implement rule objects with stable rule IDs, categories, confidence baselines, and obligation templates. At minimum cover:

| Signal | Category | Required evidence | Baseline deterministic behavior |
|---|---|---|---|
| `<` to `<=`, `>` to `>=`, equality/inequality change, threshold literal change | `boundary_change` | Old/new comparison and symbol | Generate below/at/above boundary obligations. |
| Parameter default change or newly optional/required input | `default_behavior_change` | Old/new signature | Test omitted input plus explicit old/new values. |
| Added/removed validation predicate or validator call | `validation_change` | Condition/call delta | Test newly accepted and newly rejected input. |
| Raise type changed, handler added/removed, error swallowed/propagated | `error_handling_change` | Raise/try delta | Test trigger, visible error, and recovery/fallback. |
| Assignment or allowed transition condition changed | `state_transition_change` | Assignment/condition delta | Test valid, invalid, and repeated transition. |
| Permission/role/owner/identity guard or call changed | `authorization_change` | Guard/call delta | Test allowed and denied principals; phrase assumptions explicitly. |
| Retry count, timeout, sleep, loop bound, or stop predicate changed | `retry_timeout_change` | Loop/call/comparison delta | Test recoverable, terminal, and exact limit cases. |
| Return container/field/status/type syntax changed | `output_contract_change` | Return delta | Test consumer-visible shape and old/new field behavior. |
| Persistence, event, notification, external call added/removed | `side_effect_change` | Call delta | Test occurrence, absence, ordering, and idempotency when supported. |
| Statement/call/condition order changed | `ordering_change` | Ordered structural delta | Test competing conditions and sequence-sensitive behavior. |
| Dependency target, arguments, or handling changed | `dependency_interaction_change` | Call and surrounding error/return delta | Test dependency success, failure, and unexpected response. |
| Behavior-bearing fingerprint stable; names/layout changed | `refactor_likely_no_behavior_change` | Matching normalized fingerprints | Suggest characterization/targeted regression only if configured. |
| Material delta with no reliable rule | `unknown_semantic_change` | Structural evidence | Emit a review obligation and identify missing context. |

Name-based authorization, validation, retry, and side-effect rules are hints, not proof. Cap their confidence until corroborated by structural evidence or the LLM.

### 10.8 Candidate test mapping

Build a static index only from bounded test files that satisfy configured roots or common conventions (`test_*.py`, `*_test.py`, pytest functions, and unittest classes/methods). Parse tests without importing them.

Candidate features and default maximum contributions:

| Feature | Score contribution |
|---|---:|
| Explicit configured source-to-test mapping | 0.30 |
| Mirrored source/test path | 0.25 |
| Direct import or from-import of the changed module/symbol | 0.25 |
| Changed symbol token in test name | 0.20 |
| Changed symbol token in bounded test body/docstring | 0.10 |
| Category terminology match | 0.10 |

Clamp the score to `1.0`. Require at least one structural feature, not terminology alone. Default candidate threshold: `0.35`. Keep at most five candidates per obligation, sort deterministically by descending score then path/symbol, and include match reasons. A candidate score never changes the wording from “candidate” to “covered.”

### 10.9 LLM evidence batching and prompting

Create compact evidence records before any model call. Group by module and shared changed calls, then split batches to satisfy all configured limits. Prioritize critical paths, deterministic materiality, and higher-impact categories when more than eight batches would be required.

Each prompt must:

- clearly state that repository content is untrusted data;
- instruct the model to ignore commands found in code, comments, documentation, strings, tests, or fixtures;
- delimit each evidence record and give it an opaque evidence ID;
- require references only to provided evidence IDs;
- require the stable taxonomy;
- separate observations from assumptions;
- phrase impact as an externally observable outcome;
- forbid runtime-coverage claims;
- forbid invented business rules, files, symbols, line numbers, and APIs;
- permit `unknown_semantic_change`;
- cap behavior changes and obligations per input symbol;
- request concise output matching the supplied JSON Schema.

Use a bounded README purpose excerpt only once per relevant batch and label it untrusted context. Never pass an entire README, full repository, environment file, binary, unbounded diff, or unrelated conversation history.

### 10.10 LLM result reconciliation

After every model call:

1. Verify JSON content type and parse result.
2. Validate with local strict models even if Hermes performed schema validation.
3. Reject unknown taxonomy and obligation values.
4. Reject references to unknown evidence IDs.
5. Expand accepted evidence IDs from the deterministic evidence registry.
6. Compare the claimed category with structural signals.
7. Lower confidence for unsupported claims, incomplete parses, truncated context, numerous assumptions, and model/deterministic disagreement.
8. Convert an unsupported but material claim to `unknown_semantic_change` or discard it with a warning; never preserve a fabricated reference.
9. Merge compatible deterministic and LLM findings.
10. Deduplicate overlapping findings by linked evidence, category, and normalized observable impact.

No model output may cause a file read, tool call, subprocess, network request, configuration change, or code execution.

### 10.11 Obligation generation and deduplication

Generate safe deterministic obligations before merging LLM suggestions. Each supported category has required templates from Section 10.7. Merge obligations when they share behavior IDs and equivalent normalized `given/when/then` semantics.

Deduplication should:

- lowercase and normalize whitespace/punctuation for comparison only;
- remove implementation-only wording when an equivalent observable scenario exists;
- preserve the higher-confidence phrasing;
- union behavior IDs and candidate tests;
- retain the highest priority and a deterministic origin trace;
- cap at six obligations per behavior and 100 globally;
- preserve at least one obligation for every high/critical behavior before lower-priority obligations.

When global limits are exceeded, record exactly how many obligations and behaviors were omitted and why.

### 10.12 Risk scoring

Use the specification's weighted formula:

```text
risk_score =
    behavioral_impact * 0.35
  + critical_path_weight * 0.25
  + test_gap_weight * 0.25
  + change_surface_weight * 0.15
```

All components are 0–100 and must be returned in an internal score explanation for tests, even if the compact Markdown omits the details.

Default component rules:

- `behavioral_impact`: category baseline, adjusted for public symbol, error path, state mutation, and external side effects. Security/authorization and destructive side-effect changes start higher than refactors.
- `critical_path_weight`: highest matching configured critical-path weight, otherwise a neutral low baseline rather than an assumed critical path.
- `test_gap_weight`: high when no candidate exists, medium when only weak candidates exist, and never zero because static candidates do not prove coverage.
- `change_surface_weight`: normalized from changed symbols, branches, public signature changes, cross-file reach, and side-effect/dependency deltas, capped at 100.

Labels are exact:

- 0–29: `low`;
- 30–59: `medium`;
- 60–79: `high`;
- 80–100: `critical`.

Overall risk is the maximum behavior risk, with summary counts by label. This avoids hiding a critical finding inside an average.

### 10.13 Confidence scoring

Calculate confidence independently:

```text
confidence = clamp(
    pattern_strength * 0.30
  + parser_completeness * 0.20
  + context_sufficiency * 0.15
  + evidence_agreement * 0.25
  + observability * 0.10
  - assumption_penalty
  - truncation_penalty,
  0.0,
  1.0
)
```

Rules:

- Strong deterministic operator/signature/raise deltas score higher than name-only hints.
- Parse failures and ambiguous symbol matching reduce parser completeness.
- Missing external contracts or relevant surrounding context reduce context sufficiency.
- Deterministic/LLM agreement raises evidence agreement; contradiction lowers it.
- Direct return, error, call, or state effects are more observable than internal naming changes.
- Apply a bounded penalty per material assumption.
- Apply explicit penalties for truncated files, batches, symbols, or diffs.
- Never emit high confidence without deterministic evidence.

Overall confidence is an obligation-weighted mean of emitted material behaviors, with a safe default for an empty analysis.

### 10.14 Obligation priority

Calculate integer priority from:

- linked behavior risk: 60%;
- scenario relevance to the detected category: 20%;
- apparent test gap: 15%;
- evidence confidence: 5%.

Clamp to 0–100. Sort by descending priority, then behavior ID and obligation ID for stable results.

### 10.15 Rendering

Canonical JSON rendering must be deterministic:

- use validated models;
- normalize paths;
- use stable sorting;
- omit no required fields;
- serialize UTF-8 safely;
- do not embed raw exceptions or raw model responses;
- make golden tests insensitive only to intentionally nondeterministic `analysis_id` and timing/usage fields.

Markdown must contain:

1. `## Semantic Diff Test Brief`;
2. risk, confidence, and analyzed/omitted scope;
3. inferred behavior changes with evidence;
4. prioritized checkbox obligations;
5. candidate existing tests with the static-mapping disclaimer;
6. review questions for high-risk, low-confidence items;
7. warnings and limitations, including deterministic fallback or truncation;
8. a clear statement that no tests were executed and no coverage was verified.

Escape Markdown control characters in untrusted paths/symbols and fence any compact code fragments. Keep the report concise enough for a pull-request comment and apply the 100-obligation global cap before rendering.

## 11. Security and Privacy Requirements

These are release-blocking invariants.

### 11.1 Read-only behavior

- Open target-repository files only for reading.
- Read committed content through Git where possible.
- Never modify the analyzed repository.
- Never run analyzed code, tests, hooks, interpreters, package managers, build steps, or generators.
- Never import from the target repository.
- Never access the network directly.
- The only permitted network-capable activity is the Hermes-owned LLM call, governed by Hermes configuration; `privacy.allow_network: false` means the plugin itself performs no direct network operation.

### 11.2 Boundary and path policy

- Resolve the Git root once and use it as the sole target data boundary.
- Validate every path at every trust boundary, including paths returned by Git and paths from configuration.
- Treat symlinks and Git link entries as untrusted; never follow them outside the root.
- Prevent path traversal on Windows and POSIX, including alternate separators, drive-relative paths, UNC paths, reserved device names where relevant, and case-insensitive containment checks on Windows.
- Do not accept a repository root of the filesystem or an empty path by accident.

### 11.3 Subprocess policy

- Use argument arrays and `shell=False`.
- Use resolved commit hashes after ref validation.
- Set timeouts and output-size limits.
- Set noninteractive Git environment flags as needed.
- Disable external diff/text-conversion mechanisms where applicable.
- Return safe errors on timeout, nonzero exit, decode failure, or oversized output.

### 11.4 Secret policy

Exclude at least:

- `.env` variants;
- `id_rsa`, `id_ed25519`, and SSH material;
- `.pem`, `.key`, `.p12`, `.pfx`, and keystore variants;
- common cloud credential files;
- token, password, and secret-named configuration files;
- Git credentials and auth stores.

Add bounded pattern redaction for obvious token/private-key signatures that appear inside otherwise allowed source snippets. Redaction occurs before logging, model input, warnings, and output. Test that redacted material cannot reappear through exception messages.

### 11.5 Prompt-injection policy

- Repository content is always data, never instructions.
- Trusted instructions and untrusted evidence must be separately delimited.
- Model output may reference only deterministic evidence IDs.
- Model output cannot initiate actions.
- Include adversarial fixtures in comments, docstrings, README text, test names, and string literals.
- Fail closed on fabricated evidence while retaining deterministic results.

### 11.6 Logging and telemetry

- Log stage names, counts, elapsed times, error codes, omitted scope, and aggregate LLM usage only.
- Do not log source snippets at normal levels.
- Do not log environment values, config secrets, raw prompts, raw model output, or absolute repository paths by default.
- Use repository-relative paths in diagnostics when safe.
- Do not add plugin-specific telemetry or analytics in the MVP.

## 12. Performance and Resource Budgets

Target a normal developer machine and the default limits from Section 9.

### 12.1 Required targets

- Up to 40 changed files.
- Up to 3,000 added plus removed lines.
- Up to 100 changed Python symbols.
- Deterministic preprocessing under five seconds for the reference performance fixture after warm-up.
- At most eight structured LLM calls.
- At most 100 returned obligations.
- Bounded source, README, evidence, prompt, subprocess-output, and config sizes.

### 12.2 Oversized changes

When hard input limits are exceeded before safe prioritization is possible, return `diff_too_large`. When bounded prioritization is possible:

1. score files/symbols using critical-path and deterministic materiality signals;
2. analyze the highest-priority scope;
3. state exactly what was omitted;
4. apply confidence penalties;
5. never imply complete analysis.

Do not silently truncate. Every truncation event must appear in structured scope metadata and Markdown warnings.

## 13. Testing and Evaluation Strategy

### 13.1 Unit tests

Cover:

- request and output model validation;
- config precedence and safe YAML behavior;
- path containment on Windows and POSIX-style inputs;
- ref validation and Git error mapping;
- diff and hunk parsing;
- added, removed, renamed, copied, and binary files;
- AST extraction and qualified names;
- signature, boundary, default, exception, retry/loop, return, call, assignment, and ordering deltas;
- ambiguous symbol matching;
- every deterministic taxonomy rule;
- test discovery, scoring, reasons, caps, and stable order;
- risk, confidence, and priority boundary values;
- obligation templates, merging, deduplication, and caps;
- JSON and Markdown escaping/rendering;
- secret exclusion and redaction.

### 13.2 Golden fixtures

Create small old/new committed repository fixtures for at least:

1. `<` changed to `<=`;
2. default argument changed;
3. exception swallowed versus propagated;
4. retry predicate changed;
5. authorization guard removed;
6. output field renamed;
7. state transition condition changed;
8. dependency call/argument changed;
9. side effect added or removed;
10. ordering changed;
11. pure refactor with stable behavior;
12. ambiguous dynamic/metaprogrammed code;
13. moved/renamed function;
14. no changed Python source;
15. mixed parseable and unparseable Python;
16. oversized diff with critical-path prioritization.

Store expected canonical JSON with nondeterministic fields normalized. Golden updates must be caused by an explicit contract or algorithm change and documented in `docs/decisions.md`; do not blindly overwrite expected output.

### 13.3 LLM contract tests

Use fake `ctx.llm` implementations to test:

- valid structured response;
- `content_type == "text"`;
- empty parsed result;
- unknown category;
- fabricated evidence ID;
- valid evidence but unsupported inference;
- duplicate findings and obligations;
- excessive assumptions;
- schema validation failure;
- timeout/provider exception;
- one bounded retry;
- deterministic fallback;
- prompt-injection attempts;
- call-count, input-size, and output-size caps;
- no provider/model/profile/agent override arguments.

Live paid-model calls are optional smoke tests and are never required for a normal test run or stage gate.

### 13.4 Integration tests

Use temporary Git repositories with two or more commits. Verify:

- end-to-end analysis through `service.py`;
- JSON, Markdown, and both transport modes;
- plugin registration with a fake Hermes context;
- schema name/handler/toolset/description correctness;
- handler accepts extra keyword arguments;
- handler always returns valid JSON strings;
- registration does not call Git or the LLM;
- deterministic fallback when the fake LLM fails;
- no-source-change behavior;
- directory-plugin discovery against an installed compatible Hermes runtime when available;
- wheel installation and entry-point discovery in an isolated environment.

### 13.5 Security tests

Include adversarial cases for:

- `../` and absolute-path traversal;
- Windows drive, UNC, alternate separator, and case-folding paths;
- symlinks escaping the repository;
- malicious refs beginning with `-`;
- filenames containing spaces, newlines, shell metacharacters, and Unicode;
- malicious `.gitattributes` diff drivers;
- custom YAML tags and oversized YAML;
- secret filenames and inline token/private-key patterns;
- prompt injection in every accepted text source;
- model-generated paths and evidence IDs;
- subprocess timeout and excessive output;
- error messages attempting to echo source or environment data.

### 13.6 Performance tests

Generate deterministic synthetic repositories near the configured limits. Measure deterministic preprocessing separately from LLM time. Use a generous CI regression ceiling around the five-second target to avoid flaky hardware-dependent failures, while reporting the measured median locally.

### 13.7 Evaluation metrics

Each evaluation fixture must provide machine-readable expected material categories, evidence anchors, and required scenario concepts. Calculate:

- material finding precision;
- supported-pattern recall;
- evidence correctness;
- fabricated evidence count;
- obligation concept match;
- unknown-category frequency;
- deterministic preprocessing latency;
- LLM calls and input size.

Release gates:

- at least 80% precision for material behavior-change findings;
- at least 70% recall over the supported deterministic pattern set;
- zero fabricated evidence references;
- every high/critical behavior has at least one obligation;
- candidate tests are never described as verified coverage.

Codex must perform a separate review pass over fixture labels and goldens before accepting the metrics. Human review may improve the corpus later, but it is not a stage gate.

## 14. Continuous Integration

Add CI after the basic scaffold is operational. The matrix should include:

- Python 3.11 and the newest supported Python version;
- Windows and Linux for the main suite;
- macOS for at least one supported Python version if CI capacity permits;
- unit, contract, integration, security, and evaluation groups;
- lint and format checks;
- package build;
- wheel install/import/entry-point smoke test;
- coverage report.

Pin third-party CI actions by immutable commit SHA with a version comment. Do not place credentials in pull-request workflows. Do not run live LLM integration tests in standard CI. Cache only dependency artifacts that are safe and keyed by lock-file content.

Initial coverage target: at least 90% branch coverage for security, configuration, Git-boundary, error-mapping, scoring, and transport modules; at least 85% overall. Coverage is a supporting gate, not a substitute for behavior tests.

## 15. Traceability Matrix

| Requirement | Primary implementation | Required verification |
|---|---|---|
| Diff collection and ref validation | `git_diff.py`, `path_policy.py` | Git/path unit and integration tests |
| Structural delta extraction | `ast_diff.py` | AST unit tests and golden fixtures |
| Behavioral inference | `semantic_candidates.py`, `semantic_interpreter.py` | Rule tests, LLM contract tests, evaluation metrics |
| Test obligations | `obligations.py` | Template, link, deduplication, and cap tests |
| Existing test mapping | `test_mapper.py` | Mapping score/reason and disclaimer tests |
| Explainability | `models.py`, evidence registry, reconciler | Zero fabricated evidence evaluation gate |
| Uncertainty | `scoring.py`, `service.py`, `renderer.py` | Parse/truncation/LLM-failure fixtures |
| Stable output | `models.py`, `renderer.py` | JSON Schema and golden contract tests |
| Hermes tool registration | `plugin.py`, root `__init__.py`, `plugin.yaml` | Fake-context and real-runtime discovery tests |
| Host-owned LLM access | `semantic_interpreter.py` | Call-shape/trust-gate contract tests |
| Read-only/no execution | `git_diff.py`, `path_policy.py`, architecture | Security tests and subprocess spying |
| Limits/performance | `config.py`, `service.py`, batcher | Boundary and performance tests |
| Error handling | `errors.py`, transport adapter | One test per public error code |
| JSON/Markdown output | `renderer.py` | Snapshot/golden and escaping tests |

## 16. Implementation Stages

Each stage ends in an automated gate, not a human checkpoint. A stage is complete only when its code, tests, and relevant documentation pass.

### Stage 0: Baseline, compatibility snapshot, and scaffold

Tasks:

1. Inspect the repository and note pre-existing files and changes.
2. Record Python, Git, and Hermes versions where available.
3. Inspect the installed Hermes `register_tool` and `complete_structured` signatures or compare them with current official documentation.
4. Create `pyproject.toml`, the package directories, test directories, and root plugin files.
5. Add a minimal `plugin.yaml` and root `__init__.py` shim.
6. Add formatting, linting, pytest, and coverage configuration.
7. Add `docs/decisions.md` with the fixed decisions from Section 3 and any compatibility notes.
8. Create a fake Hermes context and a registration smoke test.
9. Ensure registration is side-effect-free and performs no LLM call.

Automated gate:

```text
python -m pytest tests/contract -q
python -m ruff check .
python -m ruff format --check .
```

Completion evidence:

- Hermes sees exactly one registered tool in the fake-context test.
- Manifest, schema name, handler, toolset, and entry point agree.
- All source files use explicit UTF-8 encodings for text I/O.

### Stage 1: Strict models, schemas, errors, and configuration

Tasks:

1. Implement strict request, config, evidence, structural-delta, behavior, obligation, candidate-test, summary, scope, LLM-status, output, and error models.
2. Generate the LLM response JSON Schema from a dedicated bounded response model.
3. Implement the Hermes tool schema exactly as Section 8.1.
4. Implement safe configuration loading, precedence, defaults, and warnings.
5. Implement stable public error mapping and safe messages.
6. Add model/schema compatibility tests and one test per config validation rule.

Automated gate:

```text
python -m pytest tests/unit/test_models.py tests/unit/test_config.py tests/unit/test_errors.py tests/contract/test_schemas.py -q
```

Completion evidence:

- Invalid taxonomy values and unknown request fields fail validation.
- All default configuration values validate.
- Unsafe YAML and path-like globs are rejected.
- Success and failure transport examples validate.

### Stage 2: Repository boundary and Git diff collector

Tasks:

1. Implement repository-root resolution and containment policy.
2. Implement safe Git command runner with timeouts and bounded output.
3. Resolve refs to full commit hashes.
4. Collect name/status, rename/copy, numstat, and unified hunk metadata.
5. Enforce early file and changed-line limits.
6. Apply include/exclude/secret/control-directory filters.
7. Read old/new committed blobs without checkout.
8. Add temporary-repository integration fixtures covering add/delete/rename/binary/no-change paths.

Automated gate:

```text
python -m pytest tests/unit/test_path_policy.py tests/unit/test_git_diff.py tests/integration/test_git_collection.py tests/security/test_git_inputs.py -q
```

Completion evidence:

- Raw refs are never used after resolution.
- No shell invocation occurs.
- Path traversal, link escape, malicious ref, and external diff-driver fixtures fail safely.
- Size-limit errors include safe counts and remediation.

### Stage 3: AST extraction, symbol matching, and structural deltas

Tasks:

1. Implement old/new Python parsing and symbol inventory.
2. Normalize signatures, behavior-bearing nodes, and fingerprints.
3. Map symbols to changed hunks.
4. Implement exact and conservative rename/move matching.
5. Extract all structural deltas in Section 10.6.
6. Preserve partial results and warnings on file-level parse failure.
7. Add focused fixtures for nested, async, decorated, renamed, and ambiguous symbols.

Automated gate:

```text
python -m pytest tests/unit/test_ast_extraction.py tests/unit/test_symbol_matching.py tests/unit/test_ast_diff.py -q
```

Completion evidence:

- Unchanged symbols outside hunks do not produce deltas.
- Formatting/docstring-only edits have stable behavior fingerprints.
- Added, removed, moved, and ambiguous symbols are represented explicitly.
- No target module is imported or executed.

### Stage 4: First vertical slice and deterministic candidate engine

Implement the specification's recommended first slice end to end:

```text
Git diff
  -> changed function extraction
  -> boundary/default/exception detection
  -> evidence records
  -> deterministic obligations
  -> canonical JSON
  -> Markdown brief
```

Tasks:

1. Create a rule interface and stable rule IDs.
2. Implement boundary, default, and exception-path rules first.
3. Create evidence IDs and validated behavior candidates.
4. Implement minimal deterministic obligation templates.
5. Implement initial scoring and rendering sufficient for the slice.
6. Add five curated golden fixtures, including a pure refactor and ambiguous code.
7. Add a service entry point that runs this bounded deterministic path.

Automated gate:

```text
python -m pytest tests/unit/test_semantic_candidates.py tests/unit/test_obligations.py tests/integration/test_vertical_slice.py tests/evaluation -q
```

Completion evidence:

- The three required patterns produce evidence-linked obligations.
- Pure refactor does not become a material behavior claim by default.
- Ambiguous code becomes a review question or warning.
- Markdown can be pasted into a pull request without manual reformatting.

### Stage 5: Candidate existing-test mapper

Tasks:

1. Discover tests by configured roots and common naming conventions.
2. Parse test imports, names, classes, methods, bounded docstrings, and safe symbol references.
3. Implement mirrored paths and explicit configured mappings.
4. Calculate scores and match reasons from Section 10.8.
5. Enforce threshold, cap, stable sorting, and mapping-incomplete status.
6. Attach candidates to obligations without changing coverage wording.

Automated gate:

```text
python -m pytest tests/unit/test_test_mapper.py tests/integration/test_candidate_mapping.py -q
```

Completion evidence:

- Terminology alone cannot create a candidate.
- All mappings are labeled unverified.
- Candidate paths remain inside the repository.
- Mapping remains useful when individual tests fail to parse.

### Stage 6: Structured semantic interpreter

Tasks:

1. Implement trusted instructions and typed untrusted evidence blocks.
2. Implement related-symbol grouping, batch limits, and eight-call prioritization.
3. Call `ctx.llm.complete_structured` using the active Hermes model without gated overrides.
4. Validate content type and locally validate parsed output.
5. Reconcile evidence IDs, categories, assumptions, and deterministic support.
6. Implement bounded retry and deterministic fallback.
7. Capture aggregate usage when supplied.
8. Add all fake-LLM contract and prompt-injection tests.

Automated gate:

```text
python -m pytest tests/contract/test_llm_call.py tests/contract/test_llm_reconciliation.py tests/security/test_prompt_injection.py -q
```

Completion evidence:

- No test observes provider/model/profile/agent override parameters.
- Fabricated evidence never enters a result.
- Prompt instructions embedded in repository data have no effect.
- LLM failure preserves deterministic output and emits an explicit warning.
- Call count and per-call input size never exceed configuration.

### Stage 7: Complete taxonomy, obligations, and scoring

Tasks:

1. Add the remaining deterministic rules from Section 10.7.
2. Implement full obligation templates and review obligations.
3. Merge deterministic and supported LLM findings.
4. Implement semantic deduplication and all per-behavior/global caps.
5. Implement exact risk, confidence, and priority formulas.
6. Add boundary tests at every score label/threshold.
7. Ensure high-risk, low-confidence findings render as review questions.

Automated gate:

```text
python -m pytest tests/unit/test_patterns.py tests/unit/test_obligations.py tests/unit/test_scoring.py tests/evaluation -q
```

Completion evidence:

- Every taxonomy category has a positive and uncertainty test.
- Every high/critical behavior has an obligation.
- Risk and confidence can diverge and are independently tested.
- Obligation counts and order are deterministic.

### Stage 8: Full orchestration and output modes

Tasks:

1. Complete the typed service pipeline.
2. Enforce prioritization and omitted-scope reporting.
3. Finalize canonical JSON and all three transport modes.
4. Finalize Markdown sections, escaping, disclaimers, and review questions.
5. Map every public exception path to an error response.
6. Add end-to-end tests for success, empty scope, partial parse, truncation, LLM fallback, and each output format.

Automated gate:

```text
python -m pytest tests/integration/test_service.py tests/integration/test_rendering.py tests/contract/test_output_schema.py -q
```

Completion evidence:

- Every handler response parses as JSON.
- JSON mode matches schema version 1.0.
- Both mode contains a schema-valid canonical analysis and matching Markdown.
- Markdown contains no unsupported coverage claim.
- Omitted scope is never silent.

### Stage 9: Hermes runtime integration

Tasks:

1. Wire the service to the closure over `ctx.llm` in `plugin.py`.
2. Verify root `__init__.py`, package `register`, manifest, and entry point all resolve to the same registration logic.
3. Test extra handler keyword arguments.
4. Test plugin enablement/discovery with a temporary Hermes home where a compatible Hermes runtime is available.
5. Test project-plugin opt-in without modifying the user's environment permanently.
6. Verify registration failure cannot crash the analysis package and analysis failure cannot crash the Hermes tool loop.
7. Document plugin discovery debugging.

Automated gate:

```text
python -m pytest tests/contract/test_registration.py tests/integration/test_hermes_discovery.py -q
```

Completion evidence:

- Exactly one non-overriding tool is registered.
- No hooks, commands, skills, or extra tools are registered.
- Directory discovery works against the tested Hermes version.
- The tool description clearly states trigger, output, and advisory behavior.

### Stage 10: Security, privacy, and performance hardening

Tasks:

1. Complete mandatory secret exclusions and inline redaction.
2. Audit all file reads and subprocess calls against the policies in Section 11.
3. Add subprocess spies proving no analyzed code or non-Git executable runs.
4. Add resource exhaustion, timeout, oversized output, and Unicode tests.
5. Add generated near-limit performance fixtures.
6. Optimize deterministic preprocessing only after measuring bottlenecks.
7. Verify all truncation and omission paths are visible.
8. Write `docs/security.md` with threat model, trust boundaries, and invariants.

Automated gate:

```text
python -m pytest tests/security tests/performance -q
```

Completion evidence:

- No secret fixture content appears in model input, logs, output, or errors.
- No path escapes the repository boundary.
- Deterministic preprocessing meets the reference target or has a documented measured exception with a bounded regression test.
- Oversized inputs fail or prioritize safely without silent truncation.

### Stage 11: Full evaluation and regression stabilization

Tasks:

1. Complete all golden fixtures listed in Section 13.2.
2. Add machine-readable labels and evaluation calculations.
3. Run a separate Codex review pass over evidence anchors, labels, and expected obligations.
4. Measure precision, recall, evidence correctness, and fabricated evidence.
5. Fix false positives before expanding recall-oriented rules.
6. Run the entire test suite repeatedly enough to expose order dependence or nondeterminism.
7. Run tests with LLM disabled and with fake successful/failing LLMs.
8. Produce `docs/evaluation.md` with corpus limits and results.

Automated gate:

```text
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Completion evidence:

- All evaluation release gates pass.
- Tests pass in random or reversed file order when practical.
- No live LLM credential is needed.
- The deterministic fallback is a first-class tested mode.

### Stage 12: Documentation, packaging, and release readiness

Tasks:

1. Write the README with problem statement, advisory limitations, install/enable steps, tool input examples, output examples, configuration, and troubleshooting.
2. Complete architecture, configuration, security, decisions, and evaluation documentation.
3. Add version and changelog for `0.1.0`.
4. Build wheel and source archive.
5. Install the wheel into an isolated environment and verify import and `hermes_agent.plugins` entry-point discovery.
6. Inspect built artifacts to ensure required modules are present and fixtures/secrets/caches are absent.
7. Run final tests against the built artifact where feasible.
8. Produce a release checklist, but do not publish or push without separate authorization.

Automated gate:

```text
python -m build
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Completion evidence:

- A clean environment can install and discover the plugin.
- User and project directory installation instructions are correct.
- The package contains no credentials, local absolute paths, caches, or test-only runtime dependencies.
- Documentation states that analyses are inferred, tests are not executed, and candidate mappings do not prove coverage.

## 17. MVP Definition of Done

The MVP is complete only when all items below are true:

- [ ] A caller can analyze a local Python Git repository with `repo_path` and `base_ref`; `head_ref` defaults to `HEAD`.
- [ ] The Hermes plugin loads from a valid `plugin.yaml` and `__init__.py` and registers exactly `analyze_semantic_diff`.
- [ ] The handler accepts `(args, **kwargs)` and always returns a valid JSON string.
- [ ] The plugin returns schema-versioned canonical JSON.
- [ ] JSON, Markdown, and both modes work.
- [ ] Boundary, default argument, exception path, retry/loop limit, and function signature changes are detected deterministically.
- [ ] All material behaviors include deterministic evidence and confidence.
- [ ] Every high/critical behavior has at least one linked obligation.
- [ ] Candidate tests are static, scored, explained, capped, and always labeled unverified.
- [ ] Risk and confidence are independently calculated and presented.
- [ ] High-risk, low-confidence items are review questions.
- [ ] The plugin does not modify, import, execute, build, install, or test analyzed repository code.
- [ ] Repository boundary, secret exclusion, prompt-injection, subprocess, and resource-limit tests pass.
- [ ] The plugin makes at most eight bounded structured LLM calls and uses no model/provider/profile/agent override.
- [ ] LLM unavailability returns a useful deterministic report when configured.
- [ ] Omitted or truncated scope is explicit.
- [ ] The evaluation corpus reaches at least 80% material precision and 70% supported-pattern recall.
- [ ] Fabricated evidence count is zero.
- [ ] Deterministic preprocessing meets the performance target on the reference fixture.
- [ ] The entire automated suite, lint, formatting, package build, isolated install, and discovery smoke tests pass.
- [ ] The Markdown brief requires no manual reformatting for a pull-request comment.
- [ ] README and security/architecture/configuration/evaluation documentation match actual behavior.

## 18. Final Codex Handoff Report

When implementation is finished, Codex should provide a compact handoff containing:

- outcome and version;
- important files created;
- Hermes version(s), Python version(s), and operating systems tested;
- exact test, lint, build, and package-install results;
- evaluation precision, recall, and fabricated-evidence result;
- performance measurement;
- any intentional deviations from this plan and their decision records;
- remaining non-blocking limitations;
- release/publishing actions not taken.

Do not ask for human verification of already automated gates. If a manual live-model or publication check remains, label it optional or release-specific and keep it separate from the MVP implementation result.

## 19. Authoritative References

Implementation should prefer the specification in this repository for product behavior and the current official Hermes sources for the runtime plugin contract. The following references were verified while preparing this plan:

- [Hermes Agent: Build a Hermes Plugin](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/build-a-hermes-plugin.md)
- [Hermes Agent: Plugins](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/plugins.md)
- [Hermes Agent: Plugin LLM Access](https://hermes-agent.nousresearch.com/docs/developer-guide/plugin-llm-access)
- [Hermes Agent plugin loader and `PluginContext`](https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/plugins.py)
- [Hermes Agent Python package configuration](https://github.com/NousResearch/hermes-agent/blob/main/pyproject.toml)
- [Hermes example plugins](https://github.com/NousResearch/hermes-example-plugins)

Because Hermes Agent evolves quickly, Stage 0 must re-check these contracts against the installed or targeted Hermes version and capture any minimal compatibility adjustment in tests and `docs/decisions.md`.
