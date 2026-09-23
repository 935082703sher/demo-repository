"""Telegram channel adapter over the diagnostic conversation flow.

Pure, testable core: it turns a diagnose response into a Telegram message with
inline-keyboard buttons, and drives one update (text message or button press)
through the stateless /assistant/diagnose contract while keeping the per-chat
tree/node position. Network I/O (calling diagnose, sending messages) is injected,
so the logic is tested without Telegram or a server.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

DiagnoseFn = Callable[[str, str | None, str | None, str], Awaitable[dict[str, Any]]]
SendFn = Callable[[dict[str, Any]], Awaitable[None]]


def detect_language(code: str | None) -> str:
    """Map a Telegram language_code to a supported language (uz default)."""
    return "ru" if (code or "").lower().startswith("ru") else "uz"


def render(response: dict[str, Any]) -> dict[str, Any]:
    """Turn a diagnose response into a Telegram sendMessage payload (no chat_id)."""
    text = str(response.get("reply") or "")

    if response.get("card_id"):
        extras: list[str] = []
        if response.get("official_url"):
            extras.append(f"🔗 {response['official_url']}")
        if response.get("contact"):
            extras.append(f"📞 {response['contact']}")
        sources = response.get("sources") or []
        if sources:
            names = ", ".join(str(s.get("title") or s.get("doc_id")) for s in sources)
            extras.append(f"📎 {names}")
        if extras:
            text = f"{text}\n\n" + "\n".join(extras)
        return {"text": text}

    options = response.get("options") or []
    if options:
        keyboard = [[{"text": str(o["label"]), "callback_data": str(o["value"])}] for o in options]
        return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}

    return {"text": text}


class TelegramBot:
    """Drive diagnostic turns for Telegram chats, holding per-chat position."""

    def __init__(self, diagnose: DiagnoseFn, send: SendFn) -> None:
        self._diagnose = diagnose
        self._send = send
        self._state: dict[int, tuple[str | None, str | None]] = {}

    async def handle_update(self, update: dict[str, Any]) -> None:
        parsed = self._parse(update)
        if parsed is None:
            return
        chat_id, text, language = parsed

        tree_id, node_id = self._state.get(chat_id, (None, None))
        response = await self._diagnose(text, tree_id, node_id, language)

        if response.get("card_id") or response.get("requires_human"):
            self._state.pop(chat_id, None)  # conversation ended; next message starts fresh
        else:
            self._state[chat_id] = (response.get("tree_id"), response.get("node_id"))

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
