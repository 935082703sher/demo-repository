"""Telegram bot rendering and update handling (no network / no Telegram)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.telegram_bot import TelegramBot, detect_language, render


def test_detect_language() -> None:
    assert detect_language("ru") == "ru"
    assert detect_language("ru-RU") == "ru"
    assert detect_language("uz") == "uz"
    assert detect_language(None) == "uz"


def test_render_question_builds_inline_keyboard() -> None:
    payload = render(
        {
            "reply": "Qurilma qayerdan?",
            "options": [{"value": "abroad", "label": "Chetdan"}],
            "card_id": None,
            "requires_human": False,
        }
    )
    assert payload["text"] == "Qurilma qayerdan?"
    assert payload["reply_markup"]["inline_keyboard"] == [
        [{"text": "Chetdan", "callback_data": "abroad"}]
    ]


def test_render_card_appends_contact_and_has_no_keyboard() -> None:
    payload = render(
        {
            "reply": "Bojxona kirim orderi oling.",
            "options": [],
            "card_id": "imei-customs",
            "official_url": "https://www.uzimei.uz",
            "contact": "1170",
            "sources": [{"doc_id": "faq-mnp-imei", "title": "IMEI FAQ"}],
        }
    )
    assert "reply_markup" not in payload
    assert "https://www.uzimei.uz" in payload["text"]
    assert "1170" in payload["text"]
    assert "IMEI FAQ" in payload["text"]


class _Fake:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str | None, str | None, str]] = []
        self.sent: list[dict[str, Any]] = []

    async def diagnose(
        self, message: str, tree_id: str | None, node_id: str | None, language: str
    ) -> dict[str, Any]:
        self.calls.append((message, tree_id, node_id, language))
        return self._responses.pop(0)

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


def test_handle_update_threads_state_across_turns() -> None:
    question: dict[str, Any] = {
        "reply": "Nega bloklangan?",
        "tree_id": "imei-blokdan_chiqarish",
        "node_id": "cause",
        "options": [{"value": "not_registered", "label": "Ro'yxatda yo'q"}],
        "card_id": None,
        "requires_human": False,
        "reason": None,
    }
    card: dict[str, Any] = {
        "reply": "Ro'yxatdan o'ting.",
        "tree_id": "imei-blokdan_chiqarish",
        "node_id": None,
        "options": [],
        "card_id": "imei-unblock",
        "requires_human": False,
        "reason": None,
        "contact": "1170",
    }
    fake = _Fake([question, card])
    bot = TelegramBot(fake.diagnose, fake.send)

    # Turn 1: a free-text message with no prior state.
    text_update = {"message": {"chat": {"id": 555}, "from": {"language_code": "uz"},
                               "text": "telefonim bloklandi"}}
    asyncio.run(bot.handle_update(text_update))
    assert fake.calls[0] == ("telefonim bloklandi", None, None, "uz")
    assert fake.sent[0]["chat_id"] == 555
    assert fake.sent[0]["reply_markup"]["inline_keyboard"]

    # Turn 2: a button press carries the stored tree/node as the answer.
    button_update = {
        "callback_query": {
            "id": "cq1",
            "data": "not_registered",
            "from": {"language_code": "uz"},
            "message": {"chat": {"id": 555}},
        }
    }
    asyncio.run(bot.handle_update(button_update))
    assert fake.calls[1] == ("not_registered", "imei-blokdan_chiqarish", "cause", "uz")
    assert "1170" in fake.sent[1]["text"]
    assert "reply_markup" not in fake.sent[1]  # resolution card has no buttons


def test_handle_update_ignores_non_text() -> None:
    fake = _Fake([])
    bot = TelegramBot(fake.diagnose, fake.send)
    asyncio.run(bot.handle_update({"message": {"chat": {"id": 1}, "sticker": {}}}))
    assert fake.calls == [] and fake.sent == []
