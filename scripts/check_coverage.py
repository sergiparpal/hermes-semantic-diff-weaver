"""Enforce the repository's overall and critical-module branch coverage policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

OVERALL_MINIMUM = 85.0
BRANCH_MINIMUM = 90.0
CRITICAL_MODULES = (
    "config.py",
    "errors.py",
    "git_diff.py",
    "path_policy.py",
    "plugin.py",
    "renderer.py",
    "scoring.py",
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/check_coverage.py COVERAGE_JSON", file=sys.stderr)
        return 2
    report_path = Path(sys.argv[1])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    overall = float(report["totals"]["percent_covered"])
    if overall < OVERALL_MINIMUM:
        failures.append(f"overall coverage {overall:.2f}% is below {OVERALL_MINIMUM:.0f}%")
    files = report["files"]
    for module in CRITICAL_MODULES:
        matches = [value for path, value in files.items() if path.endswith(f"/{module}")]
        if len(matches) != 1:
            failures.append(f"critical module {module} is missing or duplicated in the report")
            continue
        branches = float(matches[0]["summary"]["percent_branches_covered"])
        if branches < BRANCH_MINIMUM:
            failures.append(
                f"{module} branch coverage {branches:.2f}% is below {BRANCH_MINIMUM:.0f}%"
            )
    if failures:
        print("Coverage policy failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        f"Coverage policy passed: {overall:.2f}% overall and at least "
        f"{BRANCH_MINIMUM:.0f}% branches in critical modules."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
