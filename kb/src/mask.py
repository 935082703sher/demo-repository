# -*- coding: utf-8 -*-
"""
PII maskalash: FIO, telefon, IMEI, pasport, JSHSHIR/PINFL, manzil, email,
murojaat raqami, bank karta. Uzbek (lotin/kirill) va rus tillari uchun.

Har bir topilma turg'un pseudonim bilan almashtiriladi (bir xil qiymat ->
bir xil token), shunda matnning bog'lanishi saqlanadi, lekin shaxs aniqlanmaydi.
"""
import hashlib
import re
from collections import Counter

# ---------------------------------------------------------------- yordamchi
_PSEUDO_CACHE = {}


def _pseudo(kind: str, value: str, salt: str = "rtmc-kb") -> str:
    key = (kind, value)
    if key not in _PSEUDO_CACHE:
        h = hashlib.sha1((salt + kind + value.lower()).encode()).hexdigest()[:6].upper()
        _PSEUDO_CACHE[key] = f"[{kind}_{h}]"
    return _PSEUDO_CACHE[key]


# ---------------------------------------------------------------- qoidalar
# Tartib muhim: aniqroq shablonlar oldin ishlaydi.
RULES = [
    # E-mail
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}", re.U)),

    # IMEI — 15 (ba'zan 14/16) raqam, ketma-ket
    ("IMEI", re.compile(r"(?<!\d)\d{14,16}(?!\d)")),

    # JSHSHIR / PINFL — 14 raqam (IMEI'dan keyin tekshiriladi, shuning uchun
    # kontekst so'zi bilan)
    ("PINFL", re.compile(
        r"(?:JSHSHIR|JSHSHIR|ПИНФЛ|ЖШШИР|PINFL)[\s:№-]*\d{14}", re.I | re.U)),

    # Pasport seriya-raqam: AA1234567 / АА1234567
    ("PASSPORT", re.compile(r"(?<![\w])[A-ZА-Я]{2}\s?\d{7}(?![\w])", re.U)),

    # Telefon: (90) 123-45-67, +998901234567, 90 123 45 67, 55-505-00-19
    ("PHONE", re.compile(
        r"(?:\+?998[\s-]?)?\(?\d{2,3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")),

    # Qisman maskalangan telefon: (91)******-01
    ("PHONE", re.compile(r"\(?\d{2}\)?\s?[\*]{3,}-?\d{0,2}")),

    # Bank karta 16 raqam guruhlangan
    ("CARD", re.compile(r"(?<!\d)(?:\d{4}[\s-]){3}\d{4}(?!\d)")),

    # Murojaat / xat raqami: 74278-s/26-son, A-365-23-son, 1252/22-son
    ("DOCNO", re.compile(
        r"(?<![\w])[A-ZА-Яa-zа-я]?[-]?\d{2,7}[-/][\wа-яА-Я]{0,4}[-/]?\d{0,4}[-\s]?(?:son|сон)",
        re.U)),
]

# FIO: "B. Ziyayev", "S.Maxamadqulov", "Ziyayev B.B."
FIO_RULES = [
    ("FIO", re.compile(r"(?<![\w])[A-ZА-ЯЎҚҒҲ]\.\s?[A-ZА-ЯЎҚҒҲ]?\.?\s?[A-ZА-ЯЎҚҒҲ][a-zа-яўқғҳ’']{2,}(?![\w])", re.U)),
    ("FIO", re.compile(r"(?<![\w])[A-ZА-ЯЎҚҒҲ][a-zа-яўқғҳ’']{2,}\s[A-ZА-ЯЎҚҒҲ]\.\s?[A-ZА-ЯЎҚҒҲ]?\.?(?![\w])", re.U)),
    # to'liq FIO: "Karomatov Sherzodbek Baxtiyorovich"
    ("FIO", re.compile(
        r"(?<![\w])[A-ZА-ЯЎҚҒҲ][a-zа-яўқғҳ’']{2,}\s[A-ZА-ЯЎҚҒҲ][a-zа-яўқғҳ’']{2,}\s"
        r"[A-ZА-ЯЎҚҒҲ][a-zа-яўқғҳ’']*(?:ovich|evich|o‘g‘li|ogli|qizi|овна|евна|ович|евич)(?![\w])",
        re.U)),
]

# Manzil: "Toshkent sh., Olmazor tum., ... 18-А" — lekin rasmiy tashkilot
# manzillari (UZIMEI ofisi) saqlanadi, chunki ular foydali ma'lumot.
ADDRESS_WHITELIST = ["olmazor tum", "sebzor mavze", "240 ats"]
ADDRESS_RE = re.compile(
    r"[A-ZА-ЯЎҚҒҲ][\w’'‘-]*\s?(?:sh|shahri|tum|tumani|MFY|mahalla|ko‘chasi|kocha|уч|ул|р-н)\.?,?"
    r"(?:\s?[\w’'‘-]+,?){0,4}\s?\d+[-]?[A-Za-zА-Яа-я]?[-]?uy?",
    re.U)

# Maskalanmasligi kerak bo'lgan rasmiy raqamlar (normativ hujjatlar, qisqa raqamlar)
KEEP = re.compile(
    r"(?:\d{3,4}[-\s]?(?:son|сон)\s?(?:VMQ|ВМҚ|qaror|қарор|PQ|ПҚ|nizom|низом))"
    r"|(?:ЎРҚ|O‘RQ|ORQ)[-\s]?\d+"
    r"|(?:\*#06#|\*1170#|1170|1090|1050)"
    r"|(?:412\s?000|82\s?400|103\s?000|41\s?200)",
    re.U)


def mask_text(text: str, keep_org_addresses: bool = True):
    """Matnni maskalaydi. (masked_text, hits) qaytaradi."""
    hits = Counter()
    placeholders = {}

    # 1) Saqlanishi kerak bo'lgan bo'laklarni vaqtincha olib qo'yamiz
    def _stash(m):
        tok = f"\x00K{len(placeholders)}\x00"
        placeholders[tok] = m.group(0)
        return tok

    text = KEEP.sub(_stash, text)
    if keep_org_addresses:
        for w in ADDRESS_WHITELIST:
            pat = re.compile(re.escape(w), re.I)
            text = pat.sub(_stash, text)

    # 2) FIO — avval to'liq shakllar
    for kind, rx in FIO_RULES:
        def _sub(m, kind=kind):
            hits[kind] += 1
            return _pseudo(kind, m.group(0))
        text = rx.sub(_sub, text)

    # 3) Raqamli va boshqa PII
    for kind, rx in RULES:
        def _sub(m, kind=kind):
            hits[kind] += 1
            return _pseudo(kind, re.sub(r"\D", "", m.group(0)) or m.group(0))
        text = rx.sub(_sub, text)

    # 4) Manzillar
    def _addr(m):
        hits["ADDRESS"] += 1
        return _pseudo("ADDRESS", m.group(0))
    text = ADDRESS_RE.sub(_addr, text)

    # 5) Oldindan █ bilan maskalangan bo'laklarni normallashtiramiz
    text, n = re.subn(r"█{2,}", "[REDACTED]", text)
    if n:
        hits["PREMASKED"] += n

    # 6) Saqlanganlarni qaytaramiz
    for tok, orig in placeholders.items():
        text = text.replace(tok, orig)

    return text, dict(hits)


# ---------------------------------------------------------------- tekshiruv
LEAK_PATTERNS = {
    "phone": re.compile(r"(?<!\d)(?:9[0-9]|33|55|77|88)[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"),
    "imei": re.compile(r"(?<!\d)\d{15}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
    "passport": re.compile(r"(?<![\w])[A-ZА-Я]{2}\s?\d{7}(?![\w])", re.U),
}


def find_leaks(text: str):
    """Maskalashdan keyin qolib ketgan PII'ni topadi (sifat nazorati)."""
    out = {}
    for name, rx in LEAK_PATTERNS.items():
        found = rx.findall(text)
        if found:
            out[name] = found[:20]
    return out


if __name__ == "__main__":
    demo = (
        "Murojaatda bayon etilgan masala yuzasidan Siz bilan (90) 607-71-11 telefon "
        "raqami orqali bog‘lanib, IMEI 356938035643809 kodi tekshirildi. "
        "Ijr: S.Maxamadqulov Tel: 55-505-00-19(1045). "
        "Vazirlar Mahkamasining 778-son qarori va ЎРҚ-445 asosida javob berildi. "
        "*#06# kombinatsiyasi. Tarif: 82 400 so‘m."
    )
    m, h = mask_text(demo)
    print(m)
    print(h)
    print("LEAKS:", find_leaks(m))
