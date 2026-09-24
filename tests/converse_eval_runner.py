"""Runner for the /assistant/converse evaluation set.

Loads labelled cases (tests/data/converse_eval.jsonl), drives each turn through the
converse endpoint, classifies the response into a lane, and scores it against the
expectation. Deterministic: with the default app the analyzer is rule-based and
the provider is the mock, so the same input always yields the same lane. Reused by
the pytest regression guard and by scripts/eval_converse.py for a human report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

_CASES_PATH = Path(__file__).resolve().parent / "data" / "converse_eval.jsonl"


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    lines = (path or _CASES_PATH).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def classify(resp: dict[str, Any]) -> str:
    """Reduce a converse response to a single lane label.

    'card:<id>' a resolution card, 'rag' a grounded answer or its no-source
    escalation (both finish the turn without a card), 'handoff' a tree dead-end,
    'menu' a topic/tree menu, 'question' a diagnostic question, 'greeting' small talk.
    """
    if resp.get("done"):
        card_id = resp.get("card_id")
        return f"card:{card_id}" if card_id else "rag"
    if resp.get("requires_human"):
        return "handoff"
    options = [o["value"] for o in resp.get("options", [])]
    if options and all("-" in value for value in options):
        return "menu"  # option values are tree ids
    if options:
        return "question"
    return "greeting"


@dataclass
class TurnResult:
    case_id: str
    turn: int
    message: str
    expected: str
    got: str
    reason: str = ""

    @property
    def passed(self) -> bool:
        return not self.reason


@dataclass
class EvalReport:
    results: list[TurnResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failures(self) -> list[TurnResult]:
        return [r for r in self.results if not r.passed]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 1.0


def _check_turn(resp: dict[str, Any], turn: dict[str, Any]) -> tuple[str, str]:
    """Return (lane, reason); reason is empty when the turn passes."""
    got = classify(resp)
    if got != turn["expect"]:
        return got, f"lane {got!r} != expected {turn['expect']!r}"
    reply = str(resp.get("reply", "")).lower()
    for needle in turn.get("reply_has", []):
        if needle.lower() not in reply:
            return got, f"reply missing {needle!r}"
    for needle in turn.get("reply_not", []):
        if needle.lower() in reply:
            return got, f"reply should not contain {needle!r}"
    return got, ""


def run_eval(client: TestClient, cases: list[dict[str, Any]] | None = None) -> EvalReport:
    cases = cases if cases is not None else load_cases()
    report = EvalReport()
    for case in cases:
        session_id = f"eval-{case['id']}"
        for index, turn in enumerate(case["turns"]):
            resp = client.post(
                "/assistant/converse",
                json={
                    "message": turn["msg"],
                    "session_id": session_id,
                    "language": case.get("lang", "uz"),
                },
            ).json()
            got, reason = _check_turn(resp, turn)
            report.results.append(
                TurnResult(case["id"], index, turn["msg"], turn["expect"], got, reason)
            )
    return report
