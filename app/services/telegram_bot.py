"""Telegram channel adapter over the /assistant/converse case-reasoning flow.

Same brain as the web chat: each chat is one session (keyed by its chat id) and
the server holds the case state, so the bot only forwards the message and renders
the reply - a topic menu, a diagnostic question with inline buttons, or a finished
answer/resolution card. Network I/O (calling converse, sending messages) is
injected, so the logic is tested without Telegram or a server.

Telegram has no language selector like the web page, so the bot lets each chat
choose its language - with /til (a keyboard), the /uz /uzc /ru /en /kaa commands,
or a plain request like "qoraqalpoqcha gapir" - and remembers the choice for that
chat. Until a choice is made it answers in Uzbek by default.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# (message, session_id, language) -> converse response
ConverseFn = Callable[[str, str, str], Awaitable[dict[str, Any]]]
SendFn = Callable[[dict[str, Any]], Awaitable[None]]

_SUPPORTED = {"uz", "uz_cyrl", "ru", "en", "kaa"}
# New chats answer in Uzbek until the user explicitly picks another language.
_DEFAULT_LANGUAGE = "uz"

# Native language names for the picker keyboard.
_LANG_NAMES = {
    "uz": "O'zbekcha",
    "uz_cyrl": "Ўзбекча (кирилл)",
    "ru": "Русский",
    "kaa": "Qaraqalpaqsha",
    "en": "English",
}
_LANG_MENU_ORDER = ["uz", "uz_cyrl", "ru", "kaa", "en"]

# Short confirmation shown in the newly chosen language.
_LANG_SET_REPLY = {
    "uz": "Til o'zbekchaga (lotin) o'zgartirildi. Savolingizni yozing.",
    "uz_cyrl": "Тил ўзбекчага (кирилл) ўзгартирилди. Саволингизни ёзинг.",
    "ru": "Язык переключён на русский. Напишите ваш вопрос.",
    "en": "Language switched to English. Please type your question.",
    "kaa": "Til qaraqalpaqshaǵa ózgertirildi. Sorawıńızdı jazıń.",
}
_CHOOSE_LANG = "Tilni tanlang / Выберите язык / Tildi saylań:"

# Slash commands that set a language outright.
_SLASH_LANG = {
    "/uz": "uz",
    "/uzc": "uz_cyrl",
    "/uz_cyrl": "uz_cyrl",
    "/ru": "ru",
    "/en": "en",
    "/kaa": "kaa",
    "/kk": "kaa",
}
# Commands that open the language picker.
_MENU_COMMANDS = {"/til", "/lang", "/language", "/start"}

# A plain-language request switches language only when a language name appears AND
# the message is short or carries a switch intent, so an ordinary sentence that
# merely mentions a language (e.g. "o'zbekistondan keldim") does not flip it.
_LANG_TOKENS: list[tuple[str, tuple[str, ...]]] = [
    ("kaa", ("qoraqalp", "qaraqalp", "karakalp", "қарақалп", "каракалп")),
    ("ru", ("ruscha", "rus tili", "русск", "по-русски", "по русски")),
    ("en", ("inglizcha", "ingliz tili", "english", "английск")),
    ("uz_cyrl", ("kirill", "кирилл", "uzcyrl")),
    ("uz", ("o'zbekcha", "ozbekcha", "узбекча", "lotincha", "lotin tili", "latin")),
]
_INTENT_WORDS = (
    "gapir",
    "til",
    "javob",
    "yoz",
    "speak",
    "write",
    "answer",
    "reply",
    "switch",
    "language",
    "язык",
    "ответ",
    "перейд",
    "напиш",
    "пиши",
)


def requested_language(text: str) -> str | None:
    """Return the language a plain message asks to switch to, or None."""
    low = text.lower()
    stripped = low.strip()
    if stripped in _SUPPORTED:
        return stripped
    short = len(stripped.split()) <= 3
    intent = any(word in low for word in _INTENT_WORDS)
    if not (short or intent):
        return None
    for code, tokens in _LANG_TOKENS:
        if any(token in low for token in tokens):
            return code
    return None


def language_keyboard() -> dict[str, Any]:
    """Inline keyboard of the supported languages (callback data ``lang:<code>``)."""
    return {
        "inline_keyboard": [
            [{"text": _LANG_NAMES[code], "callback_data": f"lang:{code}"}]
            for code in _LANG_MENU_ORDER
        ]
    }


def render(response: dict[str, Any]) -> dict[str, Any]:
    """Turn a converse response into a Telegram sendMessage payload (no chat_id).

    The reply already carries the full card or answer text; grounded sources are
    appended as a short line, and any options become inline-keyboard buttons.
    """
    text = str(response.get("reply") or "")

    sources = response.get("sources") or []
    if sources:
        names: list[str] = []
        for source in sources:
            name = str(source.get("title") or source.get("doc_id"))
            if name and name not in names:
                names.append(name)
        if names:
            text = f"{text}\n\n📎 " + ", ".join(names)

    options = response.get("options") or []
    if options:
        keyboard = [[{"text": str(o["label"]), "callback_data": str(o["value"])}] for o in options]
        return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}

    return {"text": text}


class TelegramBot:
    """Drive converse turns for Telegram chats; the server holds the case state."""

    def __init__(self, converse: ConverseFn, send: SendFn) -> None:
        self._converse = converse
        self._send = send
        # Per-chat language choice; Uzbek by default until the user picks another.
        self._language_by_chat: dict[int, str] = {}

    async def handle_update(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if callback and callback.get("data"):
            chat_id = int(callback["message"]["chat"]["id"])
            data = str(callback["data"])
            if data.startswith("lang:"):
                await self._set_language(chat_id, data[len("lang:") :])
                return
            await self._forward(chat_id, data, self._language_for(chat_id))
            return

        message = update.get("message")
        if message and message.get("text"):
            chat_id = int(message["chat"]["id"])
            text = str(message["text"])
            lang = self._language_for(chat_id)
            command = text.strip().lower().split()[0].split("@")[0] if text.strip() else ""
            if command in _MENU_COMMANDS:
                await self._send(
                    {
                        "chat_id": chat_id,
                        "text": _CHOOSE_LANG,
                        "reply_markup": language_keyboard(),
                    }
                )
                return
            if command in _SLASH_LANG:
                await self._set_language(chat_id, _SLASH_LANG[command])
                return
            requested = requested_language(text)
            if requested is not None:
                await self._set_language(chat_id, requested)
                return
            await self._forward(chat_id, text, lang)
            return

    def _language_for(self, chat_id: int) -> str:
        """The chat's chosen language; new chats default to Uzbek until the user picks."""
        return self._language_by_chat.setdefault(chat_id, _DEFAULT_LANGUAGE)

    async def _set_language(self, chat_id: int, code: str) -> None:
        if code not in _SUPPORTED:
            return
        self._language_by_chat[chat_id] = code
        await self._send({"chat_id": chat_id, "text": _LANG_SET_REPLY[code]})

    async def _forward(self, chat_id: int, text: str, lang: str) -> None:
        response = await self._converse(text, str(chat_id), lang)
        payload = render(response)
        payload["chat_id"] = chat_id
        await self._send(payload)
