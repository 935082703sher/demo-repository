"""Review captured conversations to find where the assistant needs improving.

Usage (from the repo root):
    python -m scripts.review_interactions [path] [days]

Reads the interaction log (default: logs/interactions.jsonl, or $INTERACTION_LOG_PATH)
and prints an outcome/route summary, CSAT, the questions the knowledge base could
not answer, and the turns that did not resolve. Those messages are the best
candidates to fix (add a keyword/tree/KB entry) and to add to the eval set.

The gap lists are split into 🆕 NEW (within the last <days> days, default 3) and
older, so you focus on what just happened. Messages are already PII-redacted.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.interaction_log import read_records

_UNRESOLVED = {"menu", "handoff"}


def _is_recent(record: dict[str, Any], cutoff: datetime) -> bool:
    stamp = record.get("created_at")
    if not stamp:
        return False
    try:
        return datetime.fromisoformat(stamp) >= cutoff
    except ValueError:
        return False


def _print_split(title: str, records: list[dict[str, Any]], cutoff: datetime) -> None:
    """Print a gap list split into NEW (recent) and older, each de-duplicated."""
    new = [r for r in records if _is_recent(r, cutoff)]
    old = [r for r in records if not _is_recent(r, cutoff)]
    print(f"\n=== {title}: {len(records)}  (🆕 yangi {len(new)} / eski {len(old)}) ===")
    for label, group in (("🆕 YANGI", new), ("eski", old)):
        if not group:
            continue
        print(f"  {label}:")
        for message, count in Counter(r.get("message", "") for r in group).most_common(30):
            print(f"    {count:>3}x  {message!r}")


def main() -> int:
    args = [a for a in sys.argv[1:]]
    path = args[0] if args and not args[0].isdigit() else os.environ.get(
        "INTERACTION_LOG_PATH", "logs/interactions.jsonl"
    )
    days = next((int(a) for a in args if a.isdigit()), 3)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    rows = read_records(path)
    if not rows:
        print(f"No interactions found at {path!r}. Set INTERACTION_LOG_PATH and chat first.")
        return 0

    turns = [r for r in rows if r.get("kind", "turn") == "turn"]
    feedback = [r for r in rows if r.get("kind") == "feedback"]
    unanswered = [r for r in rows if r.get("kind") == "unanswered"]

    outcomes: Counter[str] = Counter(r.get("outcome") or "?" for r in turns)
    domains: Counter[str] = Counter(r.get("domain") or "?" for r in turns)
    cards: Counter[str] = Counter(r["card_id"] for r in turns if r.get("card_id"))

    print(f"Turns: {len(turns)}   Feedback: {len(feedback)}   (last {days}d = 🆕)   ({path})\n")
    print("Outcomes:", dict(outcomes))
    print("Domains: ", dict(domains))
    print("Cards:   ", dict(cards))

    helpful = sum(1 for r in feedback if r.get("feedback") == "helpful")
    unhelpful = sum(1 for r in feedback if r.get("feedback") == "unhelpful")
    if helpful + unhelpful:
        csat = helpful / (helpful + unhelpful)
        print(f"\nCSAT: {csat * 100:.0f}%  ({helpful} helpful / {unhelpful} unhelpful)")
        bad_cards = Counter(
            r.get("card_id") or "?" for r in feedback if r.get("feedback") == "unhelpful"
        )
        if bad_cards:
            print("Cards rated unhelpful:", dict(bad_cards))

    # The KB gap: questions the knowledge base could not answer. Author answers for
    # these (add to the KB / FAQ), then rebuild the corpus - the core improvement loop.
    if unanswered:
        _print_split("Bilim bazasidan javob topilmagan savollar", unanswered, cutoff)

    unresolved = [r for r in turns if (r.get("outcome") in _UNRESOLVED) or r.get("requires_human")]
    if unresolved:
        _print_split("Hal bo'lmagan turnlar (menyu/handoff)", unresolved, cutoff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
