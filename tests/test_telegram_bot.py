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


def test_render_menu_uses_tree_ids_as_callback_data() -> None:
    payload = render(
        {
            "reply": "IMEI bo'yicha nima kerak?",
            "options": [{"value": "imei-blokdan_chiqarish", "label": "Blokdan chiqarish"}],
            "card_id": None,
        }
    )
    assert payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == (
        "imei-blokdan_chiqarish"
    )


def test_render_card_has_no_keyboard() -> None:
    # The reply already contains the whole card (cause, steps, link, contact).
    payload = render(
        {
            "reply": "Bojxona kirim orderi oling.\n🔗 https://www.uzimei.uz\n📞 1170",
            "options": [],
            "card_id": "imei-customs",
        }
    )
    assert "reply_markup" not in payload
    assert "https://www.uzimei.uz" in payload["text"]
    assert "1170" in payload["text"]


def test_render_answer_appends_sources() -> None:
    payload = render(
        {
            "reply": "Ro'yxatdan o'tkazish 82 400 so'm.",
            "options": [],
            "card_id": None,
            "sources": [
                {"doc_id": "faq-mnp-imei", "title": "IMEI FAQ"},
                {"doc_id": "faq-mnp-imei", "title": "IMEI FAQ"},  # deduped
            ],
        }
    )
    assert "reply_markup" not in payload
    assert payload["text"].count("IMEI FAQ") == 1
    assert "📎" in payload["text"]


class _Fake:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, str]] = []
        self.sent: list[dict[str, Any]] = []

    async def converse(self, message: str, session_id: str, language: str) -> dict[str, Any]:
        self.calls.append((message, session_id, language))
        return self._responses.pop(0)

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


def test_handle_update_uses_chat_id_as_session() -> None:
    question: dict[str, Any] = {
        "reply": "Nega bloklangan?",
        "options": [{"value": "not_registered", "label": "Ro'yxatda yo'q"}],
        "card_id": None,
        "requires_human": False,
    }
    card: dict[str, Any] = {
        "reply": "Ro'yxatdan o'ting.\n📞 1170",
        "options": [],
        "card_id": "imei-unblock",
        "requires_human": False,
    }
    fake = _Fake([question, card])
    bot = TelegramBot(fake.converse, fake.send)

    # Turn 1: a free-text message; the chat id becomes the session id (no client state).
    text_update = {"message": {"chat": {"id": 555}, "from": {"language_code": "uz"},
                               "text": "telefonim bloklandi"}}
    asyncio.run(bot.handle_update(text_update))
    assert fake.calls[0] == ("telefonim bloklandi", "555", "uz")
    assert fake.sent[0]["chat_id"] == 555
    assert fake.sent[0]["reply_markup"]["inline_keyboard"]

    # Turn 2: a button press; same session id, the server holds the position.
    button_update = {
        "callback_query": {
            "id": "cq1",
            "data": "not_registered",
            "from": {"language_code": "uz"},
            "message": {"chat": {"id": 555}},
        }
    }
    asyncio.run(bot.handle_update(button_update))
    assert fake.calls[1] == ("not_registered", "555", "uz")
    assert "1170" in fake.sent[1]["text"]
    assert "reply_markup" not in fake.sent[1]  # resolution card has no buttons


def test_handle_update_ignores_non_text() -> None:
    fake = _Fake([])
    bot = TelegramBot(fake.converse, fake.send)
    asyncio.run(bot.handle_update({"message": {"chat": {"id": 1}, "sticker": {}}}))
    assert fake.calls == [] and fake.sent == []
