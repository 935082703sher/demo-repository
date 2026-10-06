"""Meta-intents: a menu rejection is not a tree answer, and the real bug is fixed.

Bug: a menu was shown, the user said "muammom bu ro'yxatda yo'q" (not in this list),
and the registration keyword in "ro'yxatda" pulled it into the registration tree,
which asked "Qurilmani qayerdan oldingiz?". A rejection must re-examine the ORIGINAL
problem via the knowledge base, then recommend 1170 - never a generic tree root.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.meta_intent import conversation_act


def _post(client: TestClient, message: str, session: str) -> dict[str, Any]:
    return dict(
        client.post("/assistant/converse", json={"message": message, "session_id": session}).json()
    )


# --- unit: conversation_act classification ---


def test_conversation_act_distinguishes_meta_from_plain_answers() -> None:
    assert conversation_act("muammom bu ro'yxatda yo'q") == "none_of_above"
    assert conversation_act("hech biri mos emas") == "none_of_above"
    assert conversation_act("boshidan boshlaylik") == "restart"
    assert conversation_act("men bunday demadim") == "correction"
    assert conversation_act("boshqa muammo bor") == "other_issue"
    # A bare "no" is a plain answer to a yes/no question, not a meta-intent.
    assert conversation_act("yo'q") is None
    # A real problem that happens to mention the registry is not a rejection.
    assert conversation_act("telefonim ro'yxatdan o'tmayapti") is None


# --- integration: the exact failing conversation ---


def test_menu_rejection_does_not_enter_registration_root() -> None:
    with TestClient(create_app()) as client:
        turn1 = _post(client, "menda signal yaxshimas shunga nima qilay", "mi-sig")
        assert turn1["options"]  # a topic menu was offered
        turn2 = _post(client, "muammom bu ro'yxatda yo'q", "mi-sig")
        reply = turn2["reply"].lower()
        assert "qayerdan" not in reply  # NOT the registration root
        assert turn2["call_1170"] is True  # re-examined, no answer -> 1170
        assert turn2["status"] == "call_1170_recommended"


def test_plain_no_still_answers_a_tree_question() -> None:
    with TestClient(create_app()) as client:
        _post(client, "telefonim royxatdan otmayapti", "mi-no")  # opens the tree
        _post(client, "abroad", "mi-no")  # imported -> customs question (over the norm?)
        body = _post(client, "yo'q", "mi-no")  # within the norm -> proceeds, not a rejection
        # "yo'q" advanced the tree (a question or a card), never the menu-rejection 1170.
        assert body["call_1170"] is False
        assert body["status"] != "call_1170_recommended"


def test_fresh_not_registered_message_is_a_real_problem() -> None:
    with TestClient(create_app()) as client:
        # No menu was awaiting: "ro'yxatda yo'q" here means "not registered", a problem.
        body = _post(client, "telefonim ro'yxatda yo'q", "mi-fresh")
        assert body["call_1170"] is False  # not treated as a menu rejection


def test_restart_resets_and_greets() -> None:
    with TestClient(create_app()) as client:
        _post(client, "telefonim royxatdan otmayapti", "mi-restart")  # mid-tree
        body = _post(client, "boshidan boshlaylik", "mi-restart")
        assert body["done"] is False
        assert "assalom" in body["reply"].lower() or "muammo" in body["reply"].lower()
