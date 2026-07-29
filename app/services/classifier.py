"""Deterministic multilingual category classification for Demo 1."""

from __future__ import annotations

import re
import unicodedata

from app.domain.enums import Category
from app.domain.schemas import ClassificationResult


def normalize_text(text: str) -> str:
    """Normalize user text for transparent keyword rules."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = folded.replace("’", "'").replace("ʻ", "'").replace("ʼ", "'")
    return " ".join(re.sub(r"[^\w:/.'-]+", " ", folded, flags=re.UNICODE).split())


_CATEGORY_TERMS: dict[Category, tuple[str, ...]] = {
    Category.IMEI: (
        "imei",
        "device registration",
        "phone registration",
        "qurilma ro'yxat",
        "telefon ro'yxat",
        "регистрац imei",
        "регистрац телефон",
    ),
    Category.MNP: (
        "mnp",
        "mobile number portability",
        "number portability",
        "raqamni ko'chir",
        "raqam ko'chirish",
        "перенос номера",
        "перенести номер",
    ),
    Category.NUMBER_CODES: (
        "short number",
        "number code",
        "city code",
        "region code",
        "international code",
        "qisqa raqam",
        "shahar kodi",
        "hudud kodi",
        "xalqaro kod",
        "короткий номер",
        "код города",
        "код региона",
        "международный код",
    ),
    Category.NETWORK_QUALITY: (
        "network",
        "signal",
        "mobile data",
        "internet",
        "calls",
        "sms",
        "coverage",
        "aloqa",
        "signal",
        "mobil internet",
        "qo'ng'iroq",
        "tarmoq",
        "сеть",
        "сигнал",
        "мобильный интернет",
        "звонки",
        "связь",
    ),
    Category.WEBSITE_ISSUE: (
        "website",
        "web page",
        "page url",
        "browser",
        "rtmc.uz",
        "sayt",
        "sahifa",
        "brauzer",
        "сайт",
        "страница",
        "браузер",
    ),
}


class RequestClassifier:
    """Transparent rule-based classifier; confidence values are not ML calibrated."""

    def classify(self, message: str) -> ClassificationResult:
        """Return exactly one approved category."""
        normalized = normalize_text(message)
        scores = {
            category: sum(term in normalized for term in terms)
            for category, terms in _CATEGORY_TERMS.items()
        }
        best_category, best_score = max(scores.items(), key=lambda item: item[1])
        tied = sum(score == best_score and score > 0 for score in scores.values()) > 1

        if best_score == 0 or tied:
            return ClassificationResult(
                category=Category.OTHER,
                confidence=0.35 if best_score == 0 else 0.45,
                requires_clarification=True,
                requires_human=False,
            )

        confidence = min(0.95, 0.72 + (best_score - 1) * 0.08)
        return ClassificationResult(
            category=best_category,
            confidence=confidence,
            requires_clarification=False,
            requires_human=False,
        )


def is_complaint_like(message: str) -> bool:
    """Detect problem-reporting language without treating it as verified fact."""
    normalized = normalize_text(message)
    indicators = (
        "problem",
        "issue",
        "error",
        "failed",
        "not working",
        "slow",
        "weak",
        "complaint",
        "shikoyat",
        "muammo",
        "xato",
        "ishlam",
        "sekin",
        "пожаловаться",
        "жалоб",
        "проблем",
        "ошибк",
        "не работает",
        "медлен",
        "слаб",
    )
    return any(indicator in normalized for indicator in indicators)
