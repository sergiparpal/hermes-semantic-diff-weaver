# Configuration

Configuration precedence, highest first:

1. Tool `include` and `exclude` arguments.
2. Explicit `risk_profile` YAML.
3. `.hermes/semantic-diff-weaver.yaml`.
4. `.semantic-diff-weaver.yaml`.
5. Built-in defaults.

Lists replace lower-precedence lists. Mandatory secret/control exclusions remain additive.

```yaml
version: 1
language:
  primary: python
paths:
  include: ["**/*.py"]
  exclude: ["**/migrations/**", "**/generated/**", "**/vendor/**"]
  test_roots: ["tests"]
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

Critical paths use `{pattern, weight}` entries. Mapping entries use `{source, tests}` and influence
only static candidate ranking. YAML is size-bounded and loaded with `safe_load`. Unknown sections,
custom tags, unsupported versions/languages, invalid ranges, duplicate mapping sources, absolute
patterns, drive paths, NULs, and parent traversal are rejected.
