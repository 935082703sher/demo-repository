"""TreeCoverageEvaluator: direct / partial / none for every tree, not just one."""

from __future__ import annotations

from pathlib import Path

from app.domain.diagnostics import (
    DecisionTree,
    DiagnosticBundle,
    DiagnosticNode,
    DiagnosticOption,
    LocalizedText,
    ResolutionCard,
)
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.tree_coverage import Coverage, TreeCoverageEvaluator

_REAL = TreeCoverageEvaluator(DiagnosticEngine.from_json(Path("app/data/diagnostics.json")))


def _tid(cov: Coverage) -> str | None:
    return cov.tree.id if cov.tree is not None else None


def _eval(
    message: str, *, domain: str | None = None, facts: dict[str, str] | None = None
) -> Coverage:
    return _REAL.evaluate(message, domain=domain, known_facts=facts or {})


def test_direct_keyword_match_for_each_domain_tree() -> None:
    assert _tid(_eval("telefonim ro'yxatdan o'tmayapti")) == "imei-royxatdan_otkazish"
    assert _tid(_eval("telefonim bloklandi nima qilay")) == "imei-blokdan_chiqarish"
    assert _tid(_eval("MNP arizam rad etildi")) == "mnp-mnp_ariza_rad"
    cov = _eval("telefonim bloklandi")
    assert cov.level == "direct" and cov.issue is None and cov.reason == "keyword_match"


def test_direct_for_a_covered_specific_issue() -> None:
    cov = _eval("ikkinchi imei ro'yxatdan o'tkaza olmayapman")
    assert cov.level == "direct"
    assert _tid(cov) == "imei-ikkinchi_imei"
    assert cov.issue == "secondary_imei_registration"


def test_partial_for_a_bare_or_vague_message() -> None:
    assert _eval("telefonim ishlamayapti").level == "partial"
    assert _eval("salom yordam kerak").level == "partial"


def test_direct_from_known_facts_without_keywords() -> None:
    cov = _eval("ha", domain="imei", facts={"device_origin": "imported"})
    assert cov.level == "direct"
    assert _tid(cov) == "imei-royxatdan_otkazish" and cov.reason == "facts_match"


def _mini_engine_without_second_imei() -> DiagnosticEngine:
    lt = LocalizedText(uz="x", ru="x")
    card = ResolutionCard(id="c", title=lt, probable_cause=lt, steps=[lt])
    tree = DecisionTree(
        id="imei-reg",
        domain="imei",
        case_type="reg",
        title=lt,
        keywords=["royxat", "imei"],
        root="n1",
        nodes=[
            DiagnosticNode(
                id="n1", question=lt, options=[DiagnosticOption(value="v", label=lt, card="c")]
            )
        ],
    )
    return DiagnosticEngine(DiagnosticBundle(trees=[tree], cards=[card]))


def test_none_when_a_specific_issue_has_no_covering_tree() -> None:
    # The only tree is a generic registration tree with no 'covers' for second-IMEI.
    evaluator = TreeCoverageEvaluator(_mini_engine_without_second_imei())
    cov = evaluator.evaluate(
        "ikkinchi imei ro'yxatdan o'tkaza olmayapman", domain="imei", known_facts={}
    )
    assert cov.level == "none"
    assert cov.issue == "secondary_imei_registration"
    assert cov.tree is None  # must NOT fall into the generic registration tree
