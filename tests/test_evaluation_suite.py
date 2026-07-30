"""Evaluation dataset shape and safety acceptance."""

from evaluations.run import load_cases, run_evaluation


def test_evaluation_has_twenty_cases_per_language() -> None:
    cases = load_cases()

    assert len(cases) == 60
    assert sum(case.language.value == "uz" for case in cases) == 20
    assert sum(case.language.value == "ru" for case in cases) == 20
    assert sum(case.language.value == "en" for case in cases) == 20


def test_evaluation_acceptance_gate() -> None:
    report = run_evaluation(load_cases())

    assert report["passed_cases"] == 60
    assert report["failed_cases"] == 0
    assert report["critical_hallucination_count"] == 0
