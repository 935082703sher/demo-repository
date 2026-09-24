"""Run the RTMC assistant as a Telegram bot via long polling (no public URL).

Prerequisites:
    - The API is running:  python -m uvicorn app.main:app --port 8000
    - A bot token from @BotFather.

Usage (Windows):
    set TELEGRAM_BOT_TOKEN=123456:ABC...
    set ASSISTANT_API_URL=http://127.0.0.1:8000   (optional, this is the default)
    python scripts/telegram_polling.py

The bot forwards each message/button to POST /assistant/converse (channel=telegram,
session = chat id) and replies with the topic menu, question buttons, or the
finished answer/resolution card - the same case-reasoning brain as the web chat.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.services.telegram_bot import TelegramBot  # noqa: E402


def _load_env_file() -> None:
    """Load TELEGRAM_BOT_TOKEN (and others) from the repo .env if present."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_ROOT / ".env")


async def main() -> None:
    _load_env_file()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN o'rnatilmagan. @BotFather'dan token oling.")
        return
    api = os.environ.get("ASSISTANT_API_URL", "http://127.0.0.1:8000").rstrip("/")
    telegram = f"https://api.telegram.org/bot{token}"

    async with httpx.AsyncClient(timeout=65.0) as client:

        async def converse(message: str, session_id: str, language: str) -> dict[str, Any]:
            response = await client.post(
                f"{api}/assistant/converse",
                json={
                    "message": message,
                    "session_id": session_id,
                    "language": language,
                    "channel": "telegram",
                },
            )
            response.raise_for_status()
            return dict(response.json())

        async def send(payload: dict[str, Any]) -> None:
            await client.post(f"{telegram}/sendMessage", json=payload)

        bot = TelegramBot(converse, send)
        offset = 0
        print("Telegram bot ishga tushdi. To'xtatish: Ctrl+C")
        while True:
            try:
                updates = await client.get(
                    f"{telegram}/getUpdates", params={"offset": offset, "timeout": 50}
                )
                result = updates.json().get("result", [])
            except (httpx.HTTPError, ValueError):
                await asyncio.sleep(3.0)
                continue
            for update in result:
                offset = update["update_id"] + 1
                callback = update.get("callback_query")
                if callback:
                    await client.post(
                        f"{telegram}/answerCallbackQuery",
                        json={"callback_query_id": callback["id"]},
                    )
                try:
                    await bot.handle_update(update)
                except Exception as error:  # keep the bot alive on a single bad update
                    print(f"update xatosi: {error}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTo'xtatildi.")
