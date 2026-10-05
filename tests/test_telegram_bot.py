"""Telegram bot rendering and update handling (no network / no Telegram)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.telegram_bot import (
    TelegramBot,
    render,
    requested_language,
)


def test_requested_language_switches_on_plain_request() -> None:
    assert requested_language("qoraqalpoqcha gapir") == "kaa"
    assert requested_language("ruscha javob ber") == "ru"
    assert requested_language("answer in english please") == "en"
    assert requested_language("kirill alifbosida yoz") == "uz_cyrl"
    assert requested_language("kaa") == "kaa"


def test_requested_language_ignores_ordinary_mentions() -> None:
    # A real problem that merely mentions a place/word must not flip the language.
    assert requested_language("telefonim o'zbekistondan kelgan, ro'yxatdan o'tmayapti") is None
    assert requested_language("raqamni boshqa operatorga ko'chirmoqchiman") is None


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
    text_update = {
        "message": {
            "chat": {"id": 555},
            "from": {"language_code": "uz"},
            "text": "telefonim bloklandi",
        }
    }
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


def test_defaults_to_uzbek_regardless_of_client_locale() -> None:
    answer: dict[str, Any] = {"reply": "...", "options": [], "card_id": None}
    fake = _Fake([answer])
    bot = TelegramBot(fake.converse, fake.send)
    # A Russian-locale Telegram client still gets Uzbek by default (until it switches).
    update = {
        "message": {
            "chat": {"id": 42},
            "from": {"language_code": "ru-RU"},
            "text": "telefonim bloklandi",
        }
    }
    asyncio.run(bot.handle_update(update))
    assert fake.calls[0][2] == "uz"


def test_plain_request_switches_language_and_sticks() -> None:
    answer: dict[str, Any] = {"reply": "Qádemler...", "options": [], "card_id": None}
    fake = _Fake([answer])
    bot = TelegramBot(fake.converse, fake.send)

    # "speak Karakalpak" from a Russian-locale client: switch, confirm, no converse yet.
    switch = {
        "message": {
            "chat": {"id": 7},
            "from": {"language_code": "ru"},
            "text": "qoraqalpoqcha gapir",
        }
    }
    asyncio.run(bot.handle_update(switch))
    assert fake.calls == []  # a language switch is not forwarded to the brain
    assert fake.sent[0]["chat_id"] == 7 and "qaraqalpaqsha" in fake.sent[0]["text"].lower()

    # The next real question is forwarded in the chosen language, not the ru locale.
    question = {
        "message": {
            "chat": {"id": 7},
            "from": {"language_code": "ru"},
            "text": "telefonim royxatdan otmayapti",
        }
    }
    asyncio.run(bot.handle_update(question))
    assert fake.calls[0] == ("telefonim royxatdan otmayapti", "7", "kaa")


def test_til_command_opens_language_keyboard() -> None:
    fake = _Fake([])
    bot = TelegramBot(fake.converse, fake.send)
    asyncio.run(bot.handle_update({"message": {"chat": {"id": 9}, "from": {}, "text": "/til"}}))
    assert fake.calls == []
    buttons = fake.sent[0]["reply_markup"]["inline_keyboard"]
    callbacks = [row[0]["callback_data"] for row in buttons]
    assert "lang:kaa" in callbacks and "lang:ru" in callbacks


def test_lang_callback_sets_language_without_converse() -> None:
    fake = _Fake([])
    bot = TelegramBot(fake.converse, fake.send)
    update = {
        "callback_query": {
            "id": "cq",
            "data": "lang:en",
            "from": {"language_code": "ru"},
            "message": {"chat": {"id": 3}},
        }
    }
    asyncio.run(bot.handle_update(update))
    assert fake.calls == []
    assert "English" in fake.sent[0]["text"] or "english" in fake.sent[0]["text"].lower()
