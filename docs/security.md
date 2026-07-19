# Security and privacy

## Threat model

The repository, refs, filenames, source, tests, README text, configuration, Git metadata, and model
output are untrusted. The target may contain traversal paths, external diff drivers, symlinks,
credentials, prompt injection, invalid encodings, oversized data, or code intended to execute on
import.

## Invariants

- The target repository is never modified.
- Target code is never imported or executed; tests, hooks, interpreters, builders, package managers,
  generators, and non-Git repository tools are never run.
- Base/head refs are resolved to full commits before diff and blob commands.
- Git uses argument arrays, `shell=False`, timeouts, bounded input/output, noninteractive operation,
  disabled lazy object fetching, literal untrusted pathspecs, `--no-ext-diff`, and `--no-textconv`
  where relevant.
- Every Git/config path is normalized and checked; VCS metadata, traversal, absolute/drive/UNC paths,
  reserved device names, and mandatory secret classes are rejected or excluded.
- Repository-local config symlinks must resolve inside the repository, and both sides of a rename are
  checked so renaming a secret-looking path cannot expose its old committed content.
- Binary, oversized, non-UTF-8, credential-named, cache, environment, and control files are omitted
  visibly.
- Obvious inline token/private-key forms are redacted before evidence, model input, output, or errors.
- Decorator arguments are never retained as evidence; only bounded decorator names are recorded.
- Candidate-test indexing is bounded by per-file size and aggregate file/byte ceilings; reaching an
  aggregate ceiling marks mapping incomplete instead of silently claiming a complete index.
- Model input separates trusted instructions from delimited untrusted evidence. Output may reference
  only deterministic evidence IDs and cannot trigger reads, tools, subprocesses, network access, or
  configuration changes.
- The plugin makes no direct network request and emits no plugin telemetry.
- Resource prioritization is deterministic and applies only to explicitly configured critical paths;
  it never expands the configured file, line, symbol, evidence, or model-input ceilings.

Expected errors expose safe normalized counts or paths only. Raw source, prompts, provider responses,
environment values, credentials, and absolute repository paths are not returned.
