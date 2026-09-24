"""Regression guard: the /assistant/converse evaluation set must stay green.

Runs the labelled eval cases through the deterministic converse path (rule
analyzer + mock provider) and fails if any case regresses, printing every
mismatch so the break is obvious.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.converse_eval_runner import load_cases, run_eval


def test_converse_eval_set_all_pass() -> None:
    with TestClient(create_app()) as client:
        report = run_eval(client)
    detail = "\n".join(
        f"  [{r.case_id} turn {r.turn}] {r.message!r}: {r.reason}" for r in report.failures
    )
    assert report.failures == [], (
        f"{len(report.failures)}/{report.total} converse eval cases regressed:\n{detail}"
    )


def test_converse_eval_set_is_not_empty() -> None:
    # Guard against an accidentally empty data file silently passing the suite.
    assert len(load_cases()) >= 20
