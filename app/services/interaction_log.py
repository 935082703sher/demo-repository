"""Per-turn interaction log for offline analysis and model improvement.

Every converse turn is captured as one JSON line - the (PII-redacted) message and
the decision the assistant made (route, domain, tree/card, known facts, the reply,
sources, whether it escalated). This is the raw material for reviewing real
conversations, spotting mis-routes and gaps, and turning them into eval cases.

The message is stored already redacted, so no raw personal data reaches the log.
Logging never breaks a turn: any write error is swallowed. It is off by default
(NullInteractionLog) and enabled by setting INTERACTION_LOG_PATH.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class InteractionRecord(BaseModel):
    """One captured event: a converse turn, or a feedback signal.

    For a turn ``kind='turn'`` and the message is already PII-redacted. For a rating
    ``kind='feedback'`` and ``feedback`` is 'helpful'/'unhelpful' about the turn's
    resolution (card_id), so unhelpful ratings point straight at what to improve.
    """

    session_id: str
    channel: str
    language: str
    kind: str = "turn"
    message: str = ""
    reply: str = ""
    domain: str | None = None
    outcome: str | None = None
    card_id: str | None = None
    options: list[str] = Field(default_factory=list)
    known_facts: dict[str, str] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    requires_human: bool = False
    done: bool = False
    feedback: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


@runtime_checkable
class InteractionLog(Protocol):
    """Sink for captured turns."""

    async def record(self, record: InteractionRecord) -> None: ...


class NullInteractionLog:
    """Default no-op sink; captures nothing (tests, and logging disabled)."""

    async def record(self, record: InteractionRecord) -> None:
        return None


class JsonlInteractionLog:
    """Append each turn as one JSON line to a file, for offline analysis."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def record(self, record: InteractionRecord) -> None:
        try:
            line = json.dumps(record.model_dump(), ensure_ascii=False)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:  # pragma: no cover - logging must never break a turn
            return None


def build_interaction_log(path: str | None) -> InteractionLog:
    """A JSONL log when a path is configured, otherwise a no-op."""
    return JsonlInteractionLog(path) if path else NullInteractionLog()


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """Load captured turns (newest analysis tooling reads this)."""
    file = Path(path)
    if not file.exists():
        return []
    lines = file.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
