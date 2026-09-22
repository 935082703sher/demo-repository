# -*- coding: utf-8 -*-
"""
Javob xatlari korpusini (Murojaat ... UMUMIY) alohida kazuslarga ajratadi,
maskalaydi, tasniflaydi va JSONL sifatida yozadi.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mask import mask_text, find_leaks           # noqa: E402
from normalize import clean, detect_lang, normalize  # noqa: E402
from taxonomy import CASE_TYPES, OUTCOMES         # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Har bir javob xati shu ibora bilan boshlanadi yoki tugaydi
START_RE = re.compile(
    r"(?=^\s*(?:\d{4}[ -]?yil|Sizning|Mazkur|O‘zbekiston Respublikasi|"
    r"Murojaatda|\d{2,3}-son).{0,400}?murojaat)", re.M | re.S | re.U)
END_MARK = re.compile(
    r"(Sud organlariga murojaat qilish huquqiga egasiz\.?)", re.U)

# Har bir xatda takrorlanadigan standart matn — tasniflashdan oldin olib tashlanadi
BOILERPLATE = [
    re.compile(r"Murojaatingizni ko‘rib chiqish natijasidan norozi bo‘lsangiz.*?egasiz\.?", re.S | re.U),
    re.compile(r"Mazkur murojaatni o‘rganish bo‘yicha.*?bildirgansiz\.?", re.S | re.U),
    re.compile(r"Murojaatni o‘rganish bo‘yicha.*?bildirgansiz\.?", re.S | re.U),
    re.compile(r"Direktor(?:\s+o‘rinbosari)?.*$", re.M | re.U),
    re.compile(r"Ijr[.:].*$", re.M | re.U),
    re.compile(r"Tel[.:].*$", re.M | re.U),
]

# Imzo satri ham xat chegarasi hisoblanadi
SIGN_RE = re.compile(r"(Direktor(?:\s+o‘rinbosari)?\s*)", re.U)


def strip_boilerplate(text: str) -> str:
    for rx in BOILERPLATE:
        text = rx.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


LEGAL_RE = re.compile(
    r"(\d{3,4}-son(?:li)?\s?(?:VMQ|qaror|nizom|PQ)?"
    r"|ЎРҚ-\d+|O‘RQ-\d+"
    r"|\d{1,3}-bandi?|\d{1,2}-bob|\d{1,3}-modda)", re.U)


def split_letters(text: str):
    """Korpusni alohida javob xatlariga bo'ladi.

    Chegara: "…Sud organlariga murojaat qilish huquqiga egasiz." iborasi yoki
    undan keyingi imzo satri. Ikkalasi ham topilmasa — "yil … murojaat" boshlanishi.
    """
    # 1-bosqich: yakunlovchi ibora bo'yicha
    chunks = re.split(r"(?<=egasiz\.)|(?<=egasiz)", text)
    letters, buf = [], ""
    for c in chunks:
        buf += c
        if "Sud organlariga murojaat" in buf and len(buf.strip()) > 150:
            letters.append(buf.strip())
            buf = ""
    if len(buf.strip()) > 300:
        letters.append(buf.strip())

    # 2-bosqich: yakunlovchi iborasi yo'q, birlashib qolgan uzun bo'laklarni
    # sana bilan boshlanuvchi murojaatlar bo'yicha ehtiyotkorlik bilan bo'lamiz
    opener = re.compile(r"(?=\d{4}[ -]?yil\s+\d{1,2}[- ]?[a-zA-Z]{3,}\s+kuni)", re.U)
    out = []
    for lt in letters:
        if len(lt) > 3500:
            subs = [s.strip() for s in opener.split(lt) if len(s.strip()) > 700]
            out.extend(subs if len(subs) > 1 else [lt])
        else:
            out.append(lt)
    return out


def classify(text_norm: str, table):
    scores = {}
    for key, (_desc, kws) in table.items():
        s = sum(text_norm.count(normalize(k)) for k in kws)
        if s:
            scores[key] = s
    if not scores:
        return "boshqa"
    return max(scores, key=scores.get)


def domain_of(text_norm: str) -> str:
    imei = text_norm.count("imei") + text_norm.count("uzimei")
    mnp = text_norm.count("mnp") + text_norm.count("kochirish") + text_norm.count("operatorni almash")
    if imei == 0 and mnp == 0:
        return "boshqa"
    return "imei" if imei >= mnp else "mnp"


def build(src: Path, out: Path, doc_prefix="umumiy"):
    raw = clean(src.read_text(encoding="utf-8"))
    letters = split_letters(raw)
    rows, all_leaks = [], {}

    for i, lt in enumerate(letters, 1):
        masked, hits = mask_text(lt)
        masked = re.sub(r"\(\d{2}\)\s*-?\d{0,2}", "[PHONE]", masked)  # qoldiq fragmentlar
        norm = normalize(masked)
        norm_body = normalize(strip_boilerplate(masked))
        leaks = find_leaks(masked)
        if leaks:
            all_leaks[i] = leaks
        cid = hashlib.sha1(norm.encode()).hexdigest()[:16]
        rows.append({
            "id": f"letter-{cid}",
            "doc_id": f"{doc_prefix}-{i:04d}",
            "source_type": "javob_xati",
            "source_title": "O‘zTTBRM murojaatlarga javob xatlari (anonimlashtirilgan)",
            "authority": 4,
            "domain": domain_of(norm_body),
            "case_type": classify(norm_body, CASE_TYPES),
            "outcome": classify(norm, OUTCOMES),   # natija boilerplate'da ham bo'ladi
            "lang": detect_lang(masked),
            "text": masked,
            "text_norm": norm,
            "legal_refs": sorted(set(LEGAL_RE.findall(lt))),
            "valid_from": None,
            "pii_masked": True,
            "pii_hits": hits,
            "n_tokens": max(1, len(masked) // 3),
        })

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows, all_leaks


if __name__ == "__main__":
    rows, leaks = build(ROOT / "raw" / "murojaat_umumiy.txt",
                        ROOT / "out" / "letters.jsonl")
    print(f"xatlar: {len(rows)}")
    from collections import Counter
    print("case_type:", Counter(r["case_type"] for r in rows).most_common())
    print("outcome  :", Counter(r["outcome"] for r in rows).most_common())
    print("domain   :", Counter(r["domain"] for r in rows).most_common())
    print("lang     :", Counter(r["lang"] for r in rows).most_common())
    print("o'rtacha uzunlik:", sum(len(r['text']) for r in rows)//max(1,len(rows)))
    print("LEAK bo'lgan xatlar:", len(leaks))
    for k, v in list(leaks.items())[:5]:
        print("  ", k, v)
