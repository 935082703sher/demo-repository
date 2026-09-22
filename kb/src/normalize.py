# -*- coding: utf-8 -*-
"""
Til aniqlash va lotin/kirill normallashtirish.
Qidiruvda foydalanuvchi kirillda yozsa ham lotin hujjat topilishi uchun
har bir chunk uchun `text_norm` (lotinlashtirilgan, diakritikasiz) hosil qilinadi.
"""
import re
import unicodedata

CYR2LAT = {
    "щ": "shch", "ш": "sh", "ч": "ch", "ц": "ts", "ю": "yu", "я": "ya",
    "ё": "yo", "ж": "j", "х": "x", "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "ъ": "",
    "ь": "", "ы": "i", "э": "e",
}

LAT_FOLD = {
    "‘": "", "’": "", "'": "", "`": "", "ʼ": "", "ʻ": "",
    "o‘": "o", "g‘": "g", "oʻ": "o", "gʻ": "g",
}

RU_MARKERS = re.compile(
    r"\b(?:что|для|это|при|или|быть|который|обращени|заявлени|регистрац|устройств)\b", re.I)
UZ_CYR_MARKERS = re.compile(r"[ўқғҳ]|\b(?:ва|бўйича|учун|мурожаат|бўлган|қилиш)\b", re.I)


def detect_lang(text: str) -> str:
    """uz_latn | uz_cyrl | ru"""
    cyr = len(re.findall(r"[а-яёўқғҳ]", text, re.I))
    lat = len(re.findall(r"[a-z]", text, re.I))
    if cyr > lat:
        if UZ_CYR_MARKERS.search(text):
            return "uz_cyrl"
        if RU_MARKERS.search(text):
            return "ru"
        return "uz_cyrl"
    return "uz_latn"


def to_latin(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in CYR2LAT:
            rep = CYR2LAT[low]
            out.append(rep.upper() if ch.isupper() and rep else rep)
        else:
            out.append(ch)
    return "".join(out)


def normalize(text: str) -> str:
    """Qidiruv uchun: lotinlashtirish + apostroflarni olib tashlash + lowercase."""
    t = to_latin(text)
    for k, v in LAT_FOLD.items():
        t = t.replace(k, v)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def clean(text: str) -> str:
    """Docx artefaktlarini tozalash."""
    t = text.replace("\xa0", " ").replace("\t", " ")
    t = re.sub(r"\*\*\s*\*\*", " ", t)      # bo'sh bold
    t = re.sub(r"\*{2,}", "", t)             # markdown bold qoldiqlari
    t = re.sub(r"[ ]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
