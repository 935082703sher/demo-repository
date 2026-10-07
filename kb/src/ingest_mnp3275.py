# -*- coding: utf-8 -*-
"""
3275-son "Telekommunikatsiya xizmatlarini ko'rsatish qoidalari" (AKRV vazirining
2020-yil 30-iyundagi 208-mh-son buyrug'i, Adliya vazirligida 30.06.2020 da 3275-raqam
bilan ro'yxatdan o'tgan) ning MNP (abonent raqamini ko'chirish) bilan bog'liq BARCHA
normativ qoidalarini lex.uz eksportidan (``kb/sources/3275_30.06.2020.doc`` — aslida
HTML) tuzilgan korpusga aylantiradi:

  * ``kb/data/mnp_3275_full.json``       — qidiriladigan birliklar + metama'lumot;
  * ``kb/data/mnp_3275_full_source.txt`` — tozalangan normativ MNP matni (o'qish va
    audit uchun; HTML/CSS shovqinisiz, mazmun o'zgarmagan).

Qamrov: 3-banddagi MNP ta'riflari (donor, retsipiyent, birlamchi operator, KRMB,
KRMB operatori, lokal baza, sinxronlash, RN, All Call Query, Onward Routing, xato
ko'chirish va h.k.), II bo'lim 1-bob 10-§ to'liq (167–226-bandlar) hamda boshqa
bo'limlardagi MNPga aloqador bandlar (shartnoma, operator/abonent huquq va
majburiyatlari, to'lovlar, ma'lumotlar himoyasi). Qolgan bo'limlar (statsionar
telefon, telegraf, internet, televideniye va h.k.) MNPga tegishli emas.

lex.uz tahrir izohlari (``CHANGES_ORIGINS``) amaldagi matndan ajratiladi va
``historical_note`` sifatida saqlanadi. Ishga tushirish:

    python src/ingest_mnp3275.py [manba.doc]
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from mnp3275_data import (  # noqa: E402
    CASE_TYPES, DEF_LABELS, DEFINITIONS, DOC_TITLE, EXCERPTS, PLAIN, REJECTION_REASONS, SELECTED,
    SPLITS, TAGS, TITLES,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "3275_30.06.2020.doc"
OUT_JSON = ROOT / "data" / "mnp_3275_full.json"
OUT_TXT = ROOT / "data" / "mnp_3275_full_source.txt"
# lex.uz hujjat havolasi tasdiqlanmagan — manba sifatida yuborilgan fayl nomi saqlanadi
SOURCE_REF = "lex.uz eksporti: kb/sources/3275_30.06.2020.doc"
# Buyruq 30.06.2020 da e'lon qilingan va "rasmiy e'lon qilingan kundan e'tiboran uch oy
# o'tgach" kuchga kirgan (buyruqning 3-bandi).
IN_FORCE = "2020-09-30"

_BLOCKS = {"ACT_TEXT", "CHANGES_ORIGINS", "APPL_BANNER_LANDSCAPE_TITLE", "TEXT_HEADER_DEFAULT"}
_CLAUSE = re.compile(r"^(\d{1,3})\. (.*)$", re.S)
_NOTE_REF = re.compile(r"^\((\d{1,3})(?: va (\d{1,3}))?-(?:bandning|bandlar|band)")


def _clean(text):
    text = text.replace("‎", " ").replace("\xa0", " ")
    return " ".join(text.split())


def _blocks(path):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for el in soup.find_all(class_=True):
        cls = el.get("class")[0]
        if cls in _BLOCKS and not el.find_parent(class_=lambda c: c is not None and c in _BLOCKS):
            yield cls, _clean(el.get_text(" ", strip=True))


def parse(path=SOURCE):
    """Qoidalar (1-ilova) bandlari: band -> {section, chapter, paragraph, paras}; izohlar."""
    in_rules = False
    section = chapter = paragraph = None
    clauses, notes = {}, []
    current = None
    for cls, text in _blocks(path):
        if not text:
            continue
        if cls == "APPL_BANNER_LANDSCAPE_TITLE":
            in_rules = "1-ILOVA" in text
            continue
        if not in_rules:
            continue
        if cls == "TEXT_HEADER_DEFAULT":
            if "BOʻLIM" in text:
                section, chapter, paragraph = text, None, None
            elif re.match(r"^\d+-bob", text):
                chapter, paragraph = text, None
            else:
                paragraph = text
            continue
        if cls == "CHANGES_ORIGINS":
            m = _NOTE_REF.match(text)
            refs = [r for r in (m.groups() if m else ()) if r]
            published = re.search(r"(\d{2})\.(\d{2})\.(\d{4})-y\.", text)
            decree = re.search(r"(\d{4})-yil (\d{1,2})-(\w+?)dagi (\d+-mh)-son", text)
            notes.append({
                "refs": refs,
                "text": text.strip("() "),
                "valid_from": (f"{published.group(3)}-{published.group(2)}-{published.group(1)}"
                               if published else None),
                "decree": (f"Adliya vazirining {decree.group(4)}-son buyrugʻi "
                           f"({decree.group(1)}), roʻyxat raqami 3313" if decree else None),
            })
            continue
        m = _CLAUSE.match(text)
        if m:
            current = m.group(1)
            clauses[current] = {"section": section, "chapter": chapter,
                                "paragraph": paragraph, "paras": [m.group(2).strip()]}
        elif current:
            clauses[current]["paras"].append(text)
    return clauses, notes


def _norm(s):
    return s.lower()


def build(path=SOURCE):
    clauses, notes = parse(path)
    notes_by = {}
    for n in notes:
        for r in n["refs"]:
            # 3-bandga yagona izoh 80-xatboshi (diler ta'rifi) haqida — MNP ta'riflariga
            # tegishli emas, shuning uchun MNP ta'riflari tahrir sanasini meros qilmaydi.
            if r == "3":
                continue
            notes_by.setdefault(r, []).append(n)

    def valid_from(clause):
        dates = [n["valid_from"] for n in notes_by.get(clause, []) if n["valid_from"]]
        return max(dates) if dates else IN_FORCE

    def amended(clause):
        return sorted({n["decree"] for n in notes_by.get(clause, []) if n["decree"]})

    units = []

    def add(key, clause, title, paras, *, excerpt=False):
        loc = clauses[clause]
        units.append({
            "key": key,
            "clause": clause,
            "title": f"3275-son Qoidalar, {clause}-band. {title}",
            "plain": PLAIN.get(key, ""),
            "paragraphs": paras,
            "text": "\n".join(paras),
            "section": loc["section"],
            "chapter": loc["chapter"],
            "paragraph": loc["paragraph"],
            "excerpt": excerpt,
            "case_type": CASE_TYPES.get(key, CASE_TYPES.get(clause, "mnp_tartib")),
            "tags": list(TAGS.get(key, [])),
            "legal_refs": [f"3275-son Qoidalar, {clause}-band"],
            "valid_from": valid_from(clause),
            "amended_by": amended(clause),
            "requires_realtime_status": False,
        })

    # 3-band: MNPga tegishli ta'riflar
    for para in clauses["3"]["paras"][1:]:
        for prefix, dkey in DEFINITIONS:
            if para.startswith(prefix):
                term = DEF_LABELS.get(dkey) or para.split(" — ")[0]
                add(f"def:{dkey}", "3", f"Asosiy tushuncha: {term}", [para])
                break

    for clause in SELECTED:
        paras = clauses[clause]["paras"]
        lead = f"{clause}. "
        title = TITLES.get(clause, clauses[clause]["paragraph"] or "")
        if clause in SPLITS:
            for sub, sub_title, idx in SPLITS[clause]:
                part = [paras[i] for i in idx]
                part[0] = (lead if 0 in idx else f"{clause}-band (davomi): ") + part[0]
                add(f"{clause}#{sub}", clause, sub_title, part)
            continue
        add(clause, clause, title, [lead + paras[0], *paras[1:]])

    for clause, markers in EXCERPTS.items():
        paras = clauses[clause]["paras"]
        keep = [paras[0]] + [p for p in paras[1:] if any(_norm(m) in _norm(p) for m in markers)]
        add(clause, clause, TITLES.get(clause, ""), [f"{clause}. {keep[0]}", *keep[1:]],
            excerpt=True)
        units[-1]["title"] += " (MNPga tegishli xatboshilar)"

    # tahrir izohlari: faqat korpusga olingan bandlar bo'yicha
    included = {u["clause"] for u in units}
    hist = []
    for clause, items in sorted(notes_by.items(), key=lambda kv: int(kv[0])):
        if clause not in included:
            continue
        hist.append({
            "key": f"tarix:{clause}",
            "clause": clause,
            "title": f"3275-son Qoidalar, {clause}-band — tahrirlar tarixi",
            "text": (f"3275-son Qoidalarning {clause}-bandi qachon va qaysi hujjat bilan "
                     "oʻzgartirilgan (tarixiy izoh, amaldagi qoida emas):\n"
                     + "\n".join(f"- {n['text']}" for n in items)),
            "dates": sorted({n["valid_from"] for n in items if n["valid_from"]}),
            "decrees": sorted({n["decree"] for n in items if n["decree"]}),
            "tags": ["qachon o'zgargan", "tahrir", "o'zgartirish", "3313", "16-mh",
                     "2021-yil", "когда изменен", "редакция", "amended", "history",
                     f"{clause}-band"],
        })

    reasons = []
    for r in REJECTION_REASONS:
        reasons.append(dict(r, tags=r["tags"] + ["mnp rad etildi", "mnp nega rad etildi",
                                                 "rad sababi", "почему отказали в переносе",
                                                 "why can an mnp request be rejected"]))

    return {
        "document": DOC_TITLE,
        "source": SOURCE_REF,
        "in_force": IN_FORCE,
        "consolidated_through": max(n["valid_from"] for n in notes if n["valid_from"]),
        "units": units,
        "rejection_reasons": reasons,
        "historical_notes": hist,
        "stats": {
            "units": len(units),
            "definitions": sum(1 for u in units if u["key"].startswith("def:")),
            "clauses_167_226": len({u["clause"] for u in units
                                    if u["clause"].isdigit() and 167 <= int(u["clause"]) <= 226}),
            "rejection_reasons": len(reasons),
            "historical_notes": len(hist),
            "raw_change_notes_in_document": len(notes),
        },
    }


def source_text(data):
    """Tozalangan MNP normativ matni (audit va o'qish uchun)."""
    lines = [data["document"], f"Manba: {data['source']}",
             f"Kuchga kirgan: {data['in_force']}; konsolidatsiya: "
             f"{data['consolidated_through']}", ""]
    for u in data["units"]:
        lines.append(f"## {u['title']}")
        lines.extend(u["paragraphs"])
        lines.append("")
    lines.append("## Tahrirlar tarixi (amaldagi qoida emas)")
    for h in data["historical_notes"]:
        lines.append(h["text"])
    return "\n".join(lines) + "\n"


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    data = build(src)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    OUT_TXT.write_text(source_text(data), encoding="utf-8")
    print(json.dumps(data["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
