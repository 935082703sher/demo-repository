"""Deterministic scope classification before any provider generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.classifier import normalize_text


class ScopeStatus(StrEnum):
    """Closed outcomes for deterministic scope classification."""

    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """Explainable deterministic scope result."""

    status: ScopeStatus
    matched_signal: str | None = None


_OUT_OF_SCOPE_SIGNALS = (
    "travel",
    "travel plan",
    "book a hotel",
    "flight itinerary",
    "tourist attraction",
    "religion",
    "religious teaching",
    "political campaign",
    "political election",
    "election prediction",
    "movie",
    "music recommendation",
    "celebrity",
    "homework",
    "solve my assignment",
    "recipe",
    "medical advice",
    "diagnose my",
    "legal advice",
    "write python code",
    "debug my code",
    "capital of",
    "weather",
    "football score",
    "sayohat",
    "mehmonxona",
    "din haqida",
    "diniy",
    "siyosiy kampaniya",
    "saylov",
    "kino",
    "musiqa",
    "uy vazifasi",
    "retsept",
    "tibbiy maslahat",
    "huquqiy maslahat",
    "kod yozib",
    "ob-havo",
    "путешеств",
    "отель",
    "религи",
    "политическ",
    "выбор",
    "фильм",
    "музык",
    "домашнее задание",
    "рецепт",
    "медицинск",
    "юридическ",
    "напиши код",
    "погода",
)

_IN_SCOPE_SIGNALS = (
    "rtmc",
    "telecom",
    "telecommunication",
    "imei",
    "mnp",
    "mobile number portability",
    "number code",
    "short number",
    "city code",
    "region code",
    "mobile network",
    "mobile data",
    "signal",
    "coverage",
    "fixed internet",
    "operator",
    "rtmc.uz",
    "telekommunikatsiya",
    "mobil internet",
    "raqam ko'chir",
    "qisqa raqam",
    "shahar kodi",
    "tarmoq",
    "aloqa",
    "operator",
    "телеком",
    "мобильный интернет",
    "перенос номера",
    "короткий номер",
    "код города",
    "сеть",
    "сигнал",
    "оператор",
    "сайт rtmc",
)


class ScopeService:
    """Classify clear scope without asking an LLM to authorize itself."""

    def classify(self, message: str) -> ScopeDecision:
        """Return out-of-scope only when a configured signal is explicit."""
        normalized = normalize_text(message)
        for signal in _OUT_OF_SCOPE_SIGNALS:
            if signal in normalized:
                return ScopeDecision(ScopeStatus.OUT_OF_SCOPE, signal)
        for signal in _IN_SCOPE_SIGNALS:
            if signal in normalized:
                return ScopeDecision(ScopeStatus.IN_SCOPE, signal)
        return ScopeDecision(ScopeStatus.AMBIGUOUS)
