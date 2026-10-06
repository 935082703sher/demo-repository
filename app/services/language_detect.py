"""Pick the reply language from the weight of the incoming message.

The customer may write in Uzbek (Latin or Cyrillic), Russian, or a mix. This weighs
the message word by word and returns the language that carries the most weight, so
the answer comes back in the language they actually wrote. Uzbek is the default and
the tie-break: only a clear lead for another language switches away from it, and a
short or ambiguous message (or a control value like a button) keeps the caller's
current language, so the choice never flips on thin evidence.

It is a lightweight lexical weigher, not a full language model: it scores distinctive
letters and common function words per language. That is enough to route uz / uz_cyrl
/ ru / en reliably; Karakalpak stays opt-in (set explicitly), never auto-detected.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-zA-Zа-яёА-ЯЁўЎҚқҒғҲҳ'ʼ’oʻ]+")

# Distinctive Cyrillic letters.
_RU_ONLY = set("ыэъщ")
_UZ_CYR_LETTERS = set("ўқғҳ")

_RU_WORDS = {
    "и",
    "не",
    "что",
    "как",
    "мне",
    "нужно",
    "надо",
    "это",
    "для",
    "при",
    "по",
    "мой",
    "моя",
    "можно",
    "ли",
    "за",
    "на",
    "с",
    "сколько",
    "почему",
    "хочу",
    "нужен",
    "вы",
    "здравствуйте",
    "пожалуйста",
    "второй",
    "оплата",
    "регистрацию",
    "регистрация",
    "телефон",
    "деньги",
    "платить",
    "где",
    "когда",
    "какой",
    "меня",
    "был",
    "была",
}
_UZ_CYR_WORDS = {
    "ва",
    "бу",
    "учун",
    "керак",
    "қил",
    "рўйхат",
    "рўйхатдан",
    "мен",
    "менинг",
    "тўлов",
    "қанча",
    "иккинчи",
    "бор",
    "йўқ",
    "ўтказ",
    "бўлади",
    "қилиш",
    "олдим",
    "керакми",
}
_EN_WORDS = {
    "the",
    "is",
    "a",
    "i",
    "to",
    "my",
    "me",
    "need",
    "please",
    "how",
    "can",
    "do",
    "want",
    "you",
    "your",
    "hello",
    "register",
    "registration",
    "payment",
    "cost",
    "second",
    "customs",
    "help",
    "what",
    "why",
    "from",
    "with",
    "it",
    "and",
    "pay",
}
_UZ_LAT_WORDS = {
    "va",
    "bu",
    "uchun",
    "kerak",
    "qil",
    "royxat",
    "ro'yxat",
    "men",
    "mening",
    "tolov",
    "to'lov",
    "qancha",
    "ikkinchi",
    "bor",
    "yoq",
    "yo'q",
    "otkaz",
    "o'tkaz",
    "boladi",
    "qilishim",
    "oldim",
    "keldi",
    "qilmoqchiman",
    "royxatdan",
    "ro'yxatdan",
    "menga",
    "telefonim",
    "telefonimni",
    "nima",
    "qanday",
    "kere",
    "kerakmi",
}


def _has(chars: set[str], token: str) -> bool:
    return any(ch in chars for ch in token)


def detect_language(message: str, default: str = "uz") -> str:
    """Return the reply language (uz/uz_cyrl/ru/en) by the message's weight.

    Uzbek wins ties and ambiguity; another language is chosen only on a clear lead.
    ``default`` (the caller's current language) is returned for a short or
    signal-less message, so a button value or a terse reply does not switch language.
    """
    tokens = [t.lower() for t in _WORD.findall(message)]
    letters = [c for t in tokens for c in t if c.isalpha()]
    if len(letters) < 3:
        return default

    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    lat = len(letters) - cyr

    if cyr > lat:  # Cyrillic script: Russian vs Uzbek-Cyrillic
        ru = sum(1 for t in tokens if t in _RU_WORDS or _has(_RU_ONLY, t))
        uz = sum(1 for t in tokens if t in _UZ_CYR_WORDS or _has(_UZ_CYR_LETTERS, t))
        if uz > ru:
            return "uz_cyrl"
        if ru > uz:
            return "ru"
        # Ambiguous Cyrillic with no distinctive markers: lean Russian only when a
        # Russian-only letter appears; otherwise keep the default (often Uzbek).
        return "ru" if any(_has(_RU_ONLY, t) for t in tokens) else default

    # Latin script: English only on a clear lead, otherwise Uzbek (the default).
    en = sum(1 for t in tokens if t in _EN_WORDS)
    uz = sum(1 for t in tokens if t in _UZ_LAT_WORDS or "'" in t or "ʻ" in t or "’" in t)
    if en >= 2 and en > uz:
        return "en"
    return "uz" if default in {"uz", "en"} else default
