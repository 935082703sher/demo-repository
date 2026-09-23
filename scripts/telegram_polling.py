"""Run the RTMC assistant as a Telegram bot via long polling (no public URL).

Prerequisites:
    - The API is running:  python -m uvicorn app.main:app --port 8000
    - A bot token from @BotFather.

Usage (Windows):
    set TELEGRAM_BOT_TOKEN=123456:ABC...
    set ASSISTANT_API_URL=http://127.0.0.1:8000   (optional, this is the default)
    python scripts/telegram_polling.py

The bot forwards each message/button to POST /assistant/diagnose (channel=telegram)
and replies with the question buttons or the resolution card.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.telegram_bot import TelegramBot  # noqa: E402


async def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN o'rnatilmagan. @BotFather'dan token oling.")
        return
    api = os.environ.get("ASSISTANT_API_URL", "http://127.0.0.1:8000").rstrip("/")
    telegram = f"https://api.telegram.org/bot{token}"

    async with httpx.AsyncClient(timeout=65.0) as client:

        async def diagnose(
            message: str, tree_id: str | None, node_id: str | None, language: str
        ) -> dict[str, Any]:
            response = await client.post(
                f"{api}/assistant/diagnose",
                json={
                    "message": message,
                    "tree_id": tree_id,
                    "node_id": node_id,
                    "language": language,
                    "channel": "telegram",
                },
            )
            response.raise_for_status()
            return dict(response.json())

        async def send(payload: dict[str, Any]) -> None:
            await client.post(f"{telegram}/sendMessage", json=payload)

        bot = TelegramBot(diagnose, send)
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
