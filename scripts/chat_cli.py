"""Interactive terminal chat client for local testing.

Runs the assistant in-process (no running server or website needed) so you can
try question/answer flows straight from a terminal. Uses whatever LLM_PROVIDER
your .env selects.

    python scripts/chat_cli.py            # default language: uz
    python scripts/chat_cli.py --lang ru  # start in Russian

Type your question and press Enter. Commands: 'exit' / 'quit' / 'chiqish'.
"""

from __future__ import annotations

import argparse
import sys

from fastapi.testclient import TestClient

from app.main import create_app


def _force_utf8() -> None:
    """Avoid mojibake for Uzbek/Russian text on Windows code-page consoles."""
    for stream in (sys.stdout, sys.stdin):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main() -> None:
    _force_utf8()
    parser = argparse.ArgumentParser(description="Local RTMC AI Assistant chat")
    parser.add_argument("--lang", default="uz", choices=["uz", "ru", "en"])
    args = parser.parse_args()

    client = TestClient(create_app())
    session_id: str | None = None

    print("=" * 60)
    print("  RTMC AI Assistant — lokal chat testi")
    print(f"  Til: {args.lang}   |   Chiqish: exit / quit / chiqish")
    print("=" * 60)

    while True:
        try:
            message = input("\nSiz> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChiqildi.")
            return
        if not message:
            continue
        if message.lower() in {"exit", "quit", "chiqish"}:
            print("Chiqildi.")
            return

        payload: dict[str, object] = {"language": args.lang, "message": message}
        if session_id:
            payload["session_id"] = session_id

        response = client.post("/api/v1/chat", json=payload)
        if response.status_code != 200:
            print(f"[XATO {response.status_code}] {response.text[:300]}")
            continue

        data = response.json()
        session_id = data.get("session_id") or session_id

        print(f"\nAI> {data.get('reply', '')}")

        sources = data.get("sources") or []
        if sources:
            ids = [str(s.get('source_id', s)) if isinstance(s, dict) else str(s) for s in sources]
            print(f"    Manbalar: {', '.join(ids)}")
        if data.get("requires_human"):
            print(f"    [Operatorga yo'naltirish — sabab: {data.get('handoff_reason')}]")
        if data.get("safety_flags"):
            print(f"    [Xavfsizlik: {data.get('safety_flags')}]")
        print(
            f"    (holat: {data.get('response_type')}, "
            f"kategoriya: {data.get('category')}, grounded: {data.get('grounded')})"
        )


if __name__ == "__main__":
    main()
