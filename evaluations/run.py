"""Run the deterministic Demo 2 multilingual evaluation suite."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.domain.enums import Category, Language
from app.domain.schemas import LLMRequest, LLMResult
from app.main import create_app
from app.providers.errors import ProviderUnavailableError
from app.services.usage_limits import UsageLimitService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evaluations" / "cases" / "demo2_cases.json"
INVALID_KNOWLEDGE = ROOT / "evaluations" / "fixtures" / "invalid_knowledge.demo.json"


class EvaluationCase(BaseModel):
    """One synthetic case and its deterministic acceptance criteria."""

    model_config = ConfigDict(extra="forbid")

    id: str
    language: Language
    message: str
    scenario: str = "normal"
    initial_language: Language | None = None
    expected_response_type: str
    expected_category: Category | None = None
    expected_grounded: bool
    expected_handoff: bool
    expected_handoff_reason: str | None = None
    expected_provider_calls: int


class CountingProvider:
    """Deterministic measured provider used by the evaluation."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text=request.passages[0],
            citations=[request.source_ids[0]],
            input_tokens=12,
            output_tokens=6,
            provider_name="evaluation-mock",
            model_name="deterministic",
        )


class FailingProvider(CountingProvider):
    """Simulate a retryable provider outage."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        raise ProviderUnavailableError("synthetic evaluation outage")


class FabricatedCitationProvider(CountingProvider):
    """Attempt to introduce a source ID absent from retrieved context."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text=request.passages[0],
            citations=["FABRICATED-EVALUATION-SOURCE"],
            input_tokens=12,
            output_tokens=6,
            provider_name="evaluation-mock",
            model_name="deterministic",
        )


def load_cases(path: Path = DEFAULT_CASES) -> list[EvaluationCase]:
    """Load and validate the complete evaluation file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [EvaluationCase.model_validate(item) for item in raw]


def run_evaluation(cases: list[EvaluationCase]) -> dict[str, Any]:
    """Execute cases in isolated application instances and calculate metrics."""
    outcomes = [_run_case(case) for case in cases]
    latencies = sorted(float(outcome["latency_ms"]) for outcome in outcomes)
    by_language: dict[str, dict[str, int]] = {}
    for language in Language:
        selected = [outcome for outcome in outcomes if outcome["language"] == language.value]
        by_language[language.value] = {
            "total": len(selected),
            "passed": sum(bool(outcome["passed"]) for outcome in selected),
        }

    categorized = [outcome for outcome in outcomes if outcome["expected_category"] is not None]
    out_of_scope = [
        outcome for outcome in outcomes if outcome["expected_response_type"] == "refusal"
    ]
    expected_grounded = [outcome for outcome in outcomes if outcome["expected_grounded"]]
    unsupported = [outcome for outcome in outcomes if outcome["scenario"] == "unsupported"]
    expected_handoffs = [outcome for outcome in outcomes if outcome["expected_handoff"]]

    return {
        "suite": "rtmc-demo2-multilingual",
        "synthetic_only": True,
        "total_cases": len(outcomes),
        "passed_cases": sum(bool(outcome["passed"]) for outcome in outcomes),
        "failed_cases": sum(not bool(outcome["passed"]) for outcome in outcomes),
        "by_language": by_language,
        "category_accuracy": _ratio(
            sum(
                outcome["actual_category"] == outcome["expected_category"]
                for outcome in categorized
            ),
            len(categorized),
        ),
        "language_correctness": _ratio(
            sum(outcome["actual_language"] == outcome["language"] for outcome in outcomes),
            len(outcomes),
        ),
        "out_of_scope_refusal_accuracy": _ratio(
            sum(outcome["actual_response_type"] == "refusal" for outcome in out_of_scope),
            len(out_of_scope),
        ),
        "grounded_answer_rate": _ratio(
            sum(bool(outcome["actual_grounded"]) for outcome in expected_grounded),
            len(expected_grounded),
        ),
        "citation_validity": _ratio(
            sum(bool(outcome["citations_valid"]) for outcome in expected_grounded),
            len(expected_grounded),
        ),
        "unsupported_question_refusal_rate": _ratio(
            sum(
                outcome["actual_handoff_reason"] == "no_approved_source" for outcome in unsupported
            ),
            len(unsupported),
        ),
        "human_handoff_correctness": _ratio(
            sum(bool(outcome["actual_handoff"]) for outcome in expected_handoffs),
            len(expected_handoffs),
        ),
        "critical_hallucination_count": sum(
            bool(outcome["critical_hallucination"]) for outcome in outcomes
        ),
        "average_latency_ms": round(sum(latencies) / len(latencies), 3),
        "p95_latency_ms": round(latencies[math.ceil(len(latencies) * 0.95) - 1], 3),
        "provider_calls": sum(int(outcome["provider_calls"]) for outcome in outcomes),
        "input_tokens": sum(int(outcome["input_tokens"]) for outcome in outcomes),
        "output_tokens": sum(int(outcome["output_tokens"]) for outcome in outcomes),
        "estimated_cost": round(
            sum(float(outcome["estimated_cost"]) for outcome in outcomes),
            8,
        ),
        "scenario_counts": dict(Counter(str(case.scenario) for case in cases)),
        "failures": [
            {
                "id": outcome["id"],
                "expected_response_type": outcome["expected_response_type"],
                "actual_response_type": outcome["actual_response_type"],
                "expected_category": outcome["expected_category"],
                "actual_category": outcome["actual_category"],
            }
            for outcome in outcomes
            if not outcome["passed"]
        ],
    }


def _run_case(case: EvaluationCase) -> dict[str, Any]:
    provider: CountingProvider
    if case.scenario == "provider_failure":
        provider = FailingProvider()
    elif case.scenario == "fabricated_citation":
        provider = FabricatedCitationProvider()
    else:
        provider = CountingProvider()

    settings = Settings(
        log_level="CRITICAL",
        llm_generation_limit_per_session=(1 if case.scenario == "quota_exhaustion" else 10),
        request_rate_limit_per_minute=100,
        llm_input_cost_per_million=2,
        llm_output_cost_per_million=4,
    )
    knowledge_path = (
        INVALID_KNOWLEDGE if case.scenario in {"expired_knowledge", "inactive_knowledge"} else None
    )
    app = create_app(settings=settings, provider=provider, knowledge_path=knowledge_path)
    started = time.perf_counter()
    with TestClient(app) as client:
        response = _send_case(client, case)
    latency_ms = (time.perf_counter() - started) * 1000
    body = cast(dict[str, Any], response.json())
    usage = _usage_for(app, body)

    expected_category = case.expected_category.value if case.expected_category else None
    checks = [
        body.get("language") == case.language.value,
        body.get("response_type") == case.expected_response_type,
        body.get("grounded") is case.expected_grounded,
        body.get("requires_human") is case.expected_handoff,
        provider.calls == case.expected_provider_calls,
        body.get("officially_registered") is False,
        body.get("case_number") is None,
    ]
    if expected_category is not None:
        checks.append(body.get("category") == expected_category)
    if case.expected_handoff_reason is not None:
        checks.append(body.get("handoff_reason") == case.expected_handoff_reason)

    sources = body.get("sources") or []
    citations_valid = bool(sources) and all(
        isinstance(source, dict) and bool(source.get("document_id")) for source in sources
    )
    critical_hallucination = (
        body.get("officially_registered") is not False
        or body.get("case_number") is not None
        or (body.get("grounded") is True and not citations_valid)
        or "FABRICATED-EVALUATION-SOURCE" in response.text
    )
    return {
        "id": case.id,
        "language": case.language.value,
        "scenario": case.scenario,
        "expected_response_type": case.expected_response_type,
        "actual_response_type": body.get("response_type"),
        "expected_category": expected_category,
        "actual_category": body.get("category"),
        "expected_grounded": case.expected_grounded,
        "actual_grounded": body.get("grounded"),
        "expected_handoff": case.expected_handoff,
        "actual_handoff": body.get("requires_human"),
        "actual_handoff_reason": body.get("handoff_reason"),
        "actual_language": body.get("language"),
        "citations_valid": citations_valid,
        "critical_hallucination": critical_hallucination,
        "provider_calls": provider.calls,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "estimated_cost": usage["estimated_cost"],
        "latency_ms": latency_ms,
        "passed": all(checks) and not critical_hallucination,
    }


def _send_case(client: TestClient, case: EvaluationCase) -> Any:
    if case.scenario == "quota_exhaustion":
        first = client.post(
            "/api/v1/chat",
            json={"language": case.language.value, "message": case.message},
        )
        return client.post(
            "/api/v1/chat",
            json={"session_id": first.json()["session_id"], "message": case.message},
        )
    if case.scenario == "language_switch":
        first = client.post(
            "/api/v1/chat",
            json={
                "language": (case.initial_language or Language.EN).value,
                "message": "Give me a recipe",
            },
        )
        return client.post(
            "/api/v1/chat",
            json={
                "session_id": first.json()["session_id"],
                "language": case.language.value,
                "message": case.message,
            },
        )
    return client.post(
        "/api/v1/chat",
        json={"language": case.language.value, "message": case.message},
    )


def _usage_for(app: FastAPI, body: dict[str, Any]) -> dict[str, float | int]:
    session_id = body.get("session_id")
    if not isinstance(session_id, str):
        return {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0}
    usage = cast(UsageLimitService, app.state.usage_limits).snapshot(UUID(session_id))
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "estimated_cost": usage.estimated_cost,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def render_markdown(report: dict[str, Any]) -> str:
    """Render a concise human-readable report from machine metrics."""
    language_rows = "\n".join(
        f"| {language} | {values['passed']} | {values['total']} |"
        for language, values in report["by_language"].items()
    )
    return f"""# Demo 2 Multilingual Evaluation Report

This report is generated from synthetic fixtures only. No external provider call or
real citizen data is used.

## Result

- Cases: {report["passed_cases"]}/{report["total_cases"]} passed
- Critical hallucinations: {report["critical_hallucination_count"]}
- Category accuracy: {report["category_accuracy"]:.2%}
- Language correctness: {report["language_correctness"]:.2%}
- Out-of-scope refusal accuracy: {report["out_of_scope_refusal_accuracy"]:.2%}
- Grounded-answer rate: {report["grounded_answer_rate"]:.2%}
- Citation validity: {report["citation_validity"]:.2%}
- Unsupported-question refusal rate: {report["unsupported_question_refusal_rate"]:.2%}
- Human-handoff correctness: {report["human_handoff_correctness"]:.2%}

## Results by language

| Language | Passed | Total |
|---|---:|---:|
{language_rows}

## Performance and usage

- Average end-to-end test latency: {report["average_latency_ms"]:.3f} ms
- P95 end-to-end test latency: {report["p95_latency_ms"]:.3f} ms
- Provider attempts: {report["provider_calls"]}
- Input tokens reported by the deterministic provider: {report["input_tokens"]}
- Output tokens reported by the deterministic provider: {report["output_tokens"]}
- Estimated configured test cost: {report["estimated_cost"]:.8f}

Latency is local TestClient measurement, not production latency. Token and cost values
are deterministic synthetic measurements that prove accounting behavior; they do not
forecast an approved provider or production bill.

## Safety acceptance

Demo 2 passes the evaluation safety gate only when all 60 cases pass and the critical
hallucination count is zero. Official registration remains disabled in every case.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--json-report",
        type=Path,
        default=ROOT / "evaluations" / "reports" / "demo2_report.json",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=ROOT / "evaluations" / "reports" / "demo2_report.md",
    )
    args = parser.parse_args()
    report = run_evaluation(load_cases(args.cases))
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_report.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["failed_cases"] == 0 and report["critical_hallucination_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
