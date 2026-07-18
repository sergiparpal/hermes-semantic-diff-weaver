# Release checklist

- [ ] Choose and add an explicit license.
- [ ] Run the full tests, lint, format, coverage, evaluation, and performance gates.
- [ ] Build wheel and source distribution.
- [ ] Inspect artifacts for caches, secrets, fixtures, and local absolute paths.
- [ ] Install the wheel in an isolated environment and inspect `hermes_agent.plugins` entry points.
- [ ] Record the lowest real Hermes release passing discovery tests.
- [ ] Update changelog and evaluation measurements if behavior changed.
- [ ] Publish or push only with separate authorization.
