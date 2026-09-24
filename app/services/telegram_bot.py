"""Telegram channel adapter over the /assistant/converse case-reasoning flow.

Same brain as the web chat: each chat is one session (keyed by its chat id) and
the server holds the case state, so the bot only forwards the message and renders
the reply - a topic menu, a diagnostic question with inline buttons, or a finished
answer/resolution card. Network I/O (calling converse, sending messages) is
injected, so the logic is tested without Telegram or a server.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# (message, session_id, language) -> converse response
ConverseFn = Callable[[str, str, str], Awaitable[dict[str, Any]]]
SendFn = Callable[[dict[str, Any]], Awaitable[None]]


def detect_language(code: str | None) -> str:
    """Map a Telegram language_code to a supported language (uz default)."""
    return "ru" if (code or "").lower().startswith("ru") else "uz"


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

    async def handle_update(self, update: dict[str, Any]) -> None:
        parsed = self._parse(update)
        if parsed is None:
            return
        chat_id, text, language = parsed
        response = await self._converse(text, str(chat_id), language)
        payload = render(response)
        payload["chat_id"] = chat_id
        await self._send(payload)

    @staticmethod
    def _parse(update: dict[str, Any]) -> tuple[int, str, str] | None:
        callback = update.get("callback_query")
        if callback and callback.get("data"):
            chat_id = callback["message"]["chat"]["id"]
            language = detect_language((callback.get("from") or {}).get("language_code"))
            return int(chat_id), str(callback["data"]), language

        message = update.get("message")
        if message and message.get("text"):
            chat_id = message["chat"]["id"]
            language = detect_language((message.get("from") or {}).get("language_code"))
            return int(chat_id), str(message["text"]), language

        return None
