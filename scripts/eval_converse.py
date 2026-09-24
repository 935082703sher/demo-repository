"""Print a human-readable report for the /assistant/converse evaluation set.

Usage (from the repo root):
    python -m scripts.eval_converse

Runs every labelled case through the deterministic converse path and prints
per-case pass/fail plus overall accuracy. Use it while iterating; the pytest
guard (tests/test_converse_eval.py) enforces the same set in CI.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.converse_eval_runner import run_eval


def main() -> int:
    with TestClient(create_app()) as client:
        report = run_eval(client)
    for result in report.results:
        mark = "PASS" if result.passed else "FAIL"
        line = f"[{mark}] {result.case_id} turn {result.turn}: {result.message!r} -> {result.got}"
        if not result.passed:
            line += f"  ({result.reason})"
        print(line)
    print(
        f"\nAccuracy: {report.passed}/{report.total} = {report.accuracy * 100:.1f}%"
        f"  ({len(report.failures)} failing)"
    )
    return 0 if not report.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
