from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import check_coverage


@pytest.mark.parametrize("separator", ["/", "\\"])
def test_coverage_policy_accepts_platform_path_separators(
    tmp_path: Path, monkeypatch, separator: str
) -> None:
    report = {
        "totals": {"percent_covered": 95.0},
        "files": {
            f"hermes_semantic_diff_weaver{separator}{module}": {
                "summary": {"percent_branches_covered": 91.0}
            }
            for module in check_coverage.CRITICAL_MODULES
        },
    }
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_coverage.py", str(report_path)])

    assert check_coverage.main() == 0
