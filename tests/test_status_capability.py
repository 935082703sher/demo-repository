"""Knowledge seed v0.1 and its capability rule: never pretend to check a live system.

The assistant has no UZIMEI/MNP/customs/operator integration. A request to look up a
status gets an honest "I can't check this directly" plus a way forward; a status code
the customer pastes is explained from the seed; and composed text that claims a
lookup ("tekshirdim", "I checked") is rejected in favour of approved text.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.case_state import CaseState
from app.domain.diagnostics import ResolutionCard
from app.domain.knowledge_seed import SeedStatus, load_seed
from app.main import create_app
from app.services.card_answer import LLMCardAnswer
from app.services.status_capability import (
    APPLICATION,
    BLACKLIST,
    CUSTOMS,
    IMEI_STATUS,
    LOCATION,
    MNP_STATUS,
    MY_DEVICES,
    SEED_ENTRY_BY_KIND,
    claims_live_check,
    detect_status_request,
    reported_status_reply,
    status_request_reply,
)

_LANGS = ("uz", "uz_cyrl", "ru", "en", "kaa")
_KINDS = (IMEI_STATUS, BLACKLIST, MNP_STATUS, MY_DEVICES, CUSTOMS, APPLICATION, LOCATION)


# --- the seed ------------------------------------------------------------------


def test_seed_loads_with_valid_unique_entries() -> None:
    seed = load_seed()
    ids = [e.id for e in seed.entries]
    assert len(ids) == len(set(ids))
    assert set(seed.statuses) == set(SeedStatus)
    assert seed.capability_rule.can_find_status is False
    assert seed.capability_rule.can_explain_status is True


def test_only_published_candidates_are_stated_as_fact() -> None:
    seed = load_seed()
    for entry in seed.entries:
        assert entry.stated_as_fact == (
            entry.status is SeedStatus.PUBLISHED_CANDIDATE and not entry.review_only
        )
    review = seed.get("REVIEW-001")
    assert review is not None and not review.stated_as_fact  # tariffs need verification
    esim = seed.get("KB-ESIM-001")
    assert esim is not None and esim.status is SeedStatus.NEEDS_EXPERT_INPUT


def test_every_rule_points_at_a_real_seed_entry() -> None:
    seed = load_seed()
    for entry_id in SEED_ENTRY_BY_KIND.values():
        assert seed.get(entry_id) is not None
    for code in ("GSMA_INVALID", "CLONED", "UNKNOWN", "BLACKLISTED"):
        reported = reported_status_reply(code, "uz")
        assert reported is not None
        assert seed.by_status_code(code) is not None
        assert reported.seed_entry_id == seed.by_status_code(code).id  # type: ignore[union-attr]


# --- detecting a lookup request ---------------------------------------------------


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("IMEI statusini tekshirib bering", IMEI_STATUS),
        ("IMEI ro‘yxatdan o‘tganmi?", IMEI_STATUS),
        ("Проверьте статус IMEI", IMEI_STATUS),
        ("Can you check if my IMEI is registered?", IMEI_STATUS),
        ("Telefonim blacklistdami?", BLACKLIST),
        ("Телефоним қора рўйхатдами?", BLACKLIST),
        ("Telefonim topildi, blacklistdan chiqqanmi tekshiring.", BLACKLIST),
        ("Raqamim boshqa operatorga o‘tdimi?", MNP_STATUS),
        ("MNP statusini bilib bering", MNP_STATUS),
        ("Humans’dan Uzmobile’ga o‘tkazgandim, o‘tdimi?", MNP_STATUS),
        ("Mening nomimga qaysi qurilmalar ro‘yxatdan o‘tgan?", MY_DEVICES),
        ("Bojxonada telefonim ko‘rinadimi?", CUSTOMS),
        ("Arizam qayergacha yetdi?", APPLICATION),
        ("Telefon qayerdaligini tekshirib bering.", LOCATION),
        ("IMEI orqali topib bera olasizmi?", LOCATION),
    ],
)
def test_detects_live_status_requests(message: str, kind: str) -> None:
    assert detect_status_request(message) == kind


@pytest.mark.parametrize(
    "message",
    [
        "IMEI ro‘yxatdan o‘tmayapti",  # a problem to diagnose, not a lookup
        "IMEI statusini qanday tekshiraman?",  # how-to: the KB answers it
        "Telefonim yo‘qoldi",
        "IMEI ro'yxatdan o'tkazish qancha turadi?",
        "MNP necha kun ichida amalga oshadi?",
        "raqamni boshqa operatorga ko'chirmoqchiman",
        "Bitta telefon o‘tdi, ikkinchisi o‘tmayapti.",
    ],
)
def test_ordinary_problems_and_how_to_questions_are_not_lookups(message: str) -> None:
    assert detect_status_request(message) is None


# --- replies -----------------------------------------------------------------------


@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("kind", _KINDS)
def test_lookup_replies_exist_and_never_claim_a_check(kind: str, lang: str) -> None:
    reply = status_request_reply(kind, lang)
    assert reply.strip()
    assert not claims_live_check(reply)


@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("code", ["GSMA_INVALID", "CLONED", "UNKNOWN", "BLACKLISTED"])
def test_status_code_replies_exist_and_never_claim_a_check(code: str, lang: str) -> None:
    reported = reported_status_reply(f"UZIMEI: {code}", lang)
    assert reported is not None and reported.code == code
    assert code in reported.reply
    assert not claims_live_check(reported.reply)


def test_status_codes_match_only_as_official_tokens() -> None:
    assert reported_status_reply("an unknown device was found", "en") is None
    assert reported_status_reply("status: CLONED", "en") is not None


def test_cloned_reply_raises_the_iot_exception_and_does_not_loop_registration() -> None:
    reported = reported_status_reply("CLONED chiqdi", "uz")
    assert reported is not None
    assert "IoT" in reported.reply
    assert "qayta-qayta" in reported.reply  # explicitly: retrying will not help


@pytest.mark.parametrize(
    "text",
    [
        "IMEI'ingizni tekshirdim, hammasi joyida.",
        "Tekshirib ko'raman.",
        "Tizimdan qarayman.",
        "Я проверил ваш IMEI.",
        "I checked your IMEI and it is registered.",
        "Let me check the system for you.",
    ],
)
def test_claims_live_check_catches_pretend_lookups(text: str) -> None:
    assert claims_live_check(text)


# --- the composer guard ------------------------------------------------------------


def test_card_composer_rejects_text_that_claims_a_lookup() -> None:
    card = ResolutionCard.model_validate(
        {
            "id": "c",
            "title": {"uz": "t", "ru": "t", "en": "t"},
            "probable_cause": {"uz": "sabab", "ru": "sabab", "en": "sabab"},
            "steps": [{"uz": "qadam", "ru": "qadam", "en": "step"}],
        }
    )

    async def complete(_prompt: str) -> str:
        return '{"answer": "IMEI\'ingizni tekshirdim: hammasi joyida."}'

    composer = LLMCardAnswer(complete)
    case = CaseState(case_id="c", session_id="s", domain="imei")
    text = asyncio.run(composer.compose(card, case, "uz", "Tasdiqlangan matn."))
    assert text == "Tasdiqlangan matn."


# --- the conversation --------------------------------------------------------------


def _post(client: TestClient, message: str, session: str, lang: str = "uz") -> dict[str, Any]:
    return dict(
        client.post(
            "/assistant/converse",
            json={"message": message, "session_id": session, "language": lang},
        ).json()
    )


def test_converse_answers_a_lookup_request_honestly_and_keeps_helping() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "IMEI ro‘yxatdan o‘tganmi? Tekshirib bering", "st-1")
    assert "tekshirish imkoniyatim yo'q" in body["reply"]
    assert "yuborsangiz" in body["reply"]  # asks for what the customer sees
    assert body["done"] is False  # never a dead end
    assert body["requires_human"] is False
    assert not claims_live_check(body["reply"])


def test_converse_mnp_lookup_in_russian() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "Проверьте, мой номер перешел к другому оператору?", "st-2", "ru")
    assert "не могу" in body["reply"]


def test_converse_explains_a_reported_status_code() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "UZIMEI'da GSMA_INVALID deb chiqyapti", "st-3")
    assert body["reply"].startswith("GSMA_INVALID")
    assert "qayta-qayta" in body["reply"]


def test_lookup_request_mid_tree_keeps_the_open_question() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.case_store  # type: ignore[attr-defined]
        first = _post(client, "Telefonim chetdan olib kelingan, ro'yxatdan o'tmayapti", "st-4")
        assert first["done"] is False
        before = client.portal.call(store.get, "st-4")  # type: ignore[union-attr]
        tree, node = before.active_tree, before.pending_node
        assert tree is not None and node is not None
        second = _post(client, "IMEI statusini tekshirib bering", "st-4")
        after = client.portal.call(store.get, "st-4")  # type: ignore[union-attr]
    assert "tekshirish imkoniyatim yo'q" in second["reply"]
    assert (after.active_tree, after.pending_node) == (tree, node)
