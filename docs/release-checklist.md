# Release checklist

- [x] Choose and add an explicit license (MIT).
- [x] Run the full tests, lint, format, coverage, evaluation, and performance gates.
- [x] Build wheel and source distribution.
- [x] Inspect artifacts for caches, tests, secrets, local paths, metadata, and license inclusion.
- [x] Install the wheel in an isolated environment and inspect `hermes_agent.plugins` entry points.
- [x] Record the lowest real Hermes release passing discovery tests (0.14.0).
- [x] Test the current Hermes release (0.18.2) through pip and directory discovery.
- [x] Update changelog and evaluation measurements if behavior changed.
- [x] Publish or push only with separate authorization.
