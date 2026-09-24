"""Review captured conversations to find where the assistant needs improving.

Usage (from the repo root):
    python -m scripts.review_interactions [path]

Reads the interaction log (default: logs/interactions.jsonl, or $INTERACTION_LOG_PATH)
and prints an outcome/route summary plus the turns that did NOT resolve - those that
fell back to a topic menu or escalated to a human. Those messages are the best
candidates to fix (add a keyword/tree/KB entry) and to add to the eval set, so the
model improves over time. Messages are already PII-redacted in the log.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

from app.services.interaction_log import read_records

_UNRESOLVED = {"menu", "handoff"}


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "INTERACTION_LOG_PATH", "logs/interactions.jsonl"
    )
    rows = read_records(path)
    if not rows:
        print(f"No interactions found at {path!r}. Set INTERACTION_LOG_PATH and chat first.")
        return 0

    outcomes: Counter[str] = Counter(r.get("outcome") or "?" for r in rows)
    domains: Counter[str] = Counter(r.get("domain") or "?" for r in rows)
    cards: Counter[str] = Counter(r["card_id"] for r in rows if r.get("card_id"))

    print(f"Interactions: {len(rows)}  ({path})\n")
    print("Outcomes:", dict(outcomes))
    print("Domains: ", dict(domains))
    print("Cards:   ", dict(cards))

    unresolved = [r for r in rows if (r.get("outcome") in _UNRESOLVED) or r.get("requires_human")]
    print(f"\nImprovement candidates (unresolved): {len(unresolved)}")
    for r in unresolved:
        print(f"  [{r.get('outcome')}] ({r.get('domain')}) {r.get('message', '')!r}")

    # The messages most often left unresolved are the highest-value fixes.
    common = Counter(r.get("message", "") for r in unresolved).most_common(10)
    if common:
        print("\nMost frequent unresolved messages:")
        for message, count in common:
            print(f"  {count:>3}x  {message!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
