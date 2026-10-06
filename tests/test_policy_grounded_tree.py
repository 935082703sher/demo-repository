"""Decision-tree resolutions are bound to VMQ-778 and cite their legal basis.

The tree stays a diagnostic/fact-finding instrument; the final answer carries the
clause citation of the rules the card is grounded in, and those rule ids are known
to the policy bundle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.domain.diagnostics import DiagnosticBundle, ResolutionCard
from app.main import create_app
from app.services.policy_matcher import PolicyMatcher

_DIAG = Path("app/data/diagnostics.json")
_RULES = Path("app/data/policy_rules.json")


def _cards() -> dict[str, ResolutionCard]:
    bundle = DiagnosticBundle.model_validate(json.loads(_DIAG.read_text(encoding="utf-8")))
    return {card.id: card for card in bundle.cards}


def _post(client: TestClient, message: str, session: str) -> dict[str, Any]:
    return dict(
        client.post("/assistant/converse", json={"message": message, "session_id": session}).json()
    )


def test_every_card_policy_rule_id_exists_in_the_bundle() -> None:
    known = {rule.rule_id for rule in PolicyMatcher.from_json(_RULES).rules}
    cards = _cards()
    annotated = 0
    for card in cards.values():
        for rule_id in card.policy_rule_ids:
            assert rule_id in known, f"{card.id} cites unknown rule {rule_id}"
        annotated += bool(card.policy_rule_ids)
    assert annotated >= 10  # the IMEI resolution cards are grounded


def test_imei_cards_are_grounded_in_vmq778() -> None:
    cards = _cards()
    assert "per_imei_separate_payment" in cards["imei-second-online"].policy_rule_ids
    assert "clone_or_undetermined_not_registered" in cards["imei-clone"].policy_rule_ids
    # MNP cards rest on a different regulation, so they carry no VMQ-778 rules.
    assert cards["mnp-docs"].policy_rule_ids == []


def test_second_imei_resolution_cites_per_imei_clause() -> None:
    with TestClient(create_app()) as client:
        _post(client, "O'zbekistonda do'kondan oldim, ikkinchi IMEI ro'yxatda yo'q", "gt-2imei")
        body = _post(client, "ikkalasi deklaratsiyada bor", "gt-2imei")
        assert body["status"] == "resolved"
        assert "Huquqiy asos" in body["reply"]  # the legal basis is cited
        clauses = [s["doc_id"] for s in (body.get("sources") or [])]
        assert any("6-ilova" in c for c in clauses)  # per-IMEI payment clause
