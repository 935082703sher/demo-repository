# -*- coding: utf-8 -*-
"""
VMQ 778-son (17.09.2019) qarori va Nizomining TO'LIQ konsolidatsiyalangan matnini
lex.uz eksportidan (``kb/sources/vmq778_17.09.2019.doc`` — aslida HTML) tuzilgan
korpusga aylantiradi: ``kb/data/vmq778_full.json``.

Nima qiladi:
  * qarorning asosiy qismi, Nizomning barcha boblari, bandlari (6¹, 10², 49³ kabi
    ustki indeksli bandlar ham), 2-banddagi har bir ta'rif va barcha ilovalar
    (qurilma turlari ro'yxati, sxemalar, anketa shakllari, tarif jadvali)
    alohida qidiriladigan birlik (unit) bo'ladi;
  * lex.uz tahrir izohlari (``CHANGES_ORIGINS`` — "... qarori tahririda",
    "... kiritilgan", "... o'z kuchini yo'qotgan") amaldagi matndan AJRATILADI va
    ``temporal_status = historical_note`` sifatida tegishli band bo'yicha
    guruhlanadi — eski tahrir hech qachon amaldagi qoida bilan aralashmaydi;
  * 2019-yilgi o'tish davri qoidalari va bajarilgan bir martalik topshiriqlar
    ``temporal_status = historical`` bo'ladi;
  * har bir birlikka amaldagi tahririning kuchga kirish sanasi (``valid_from``),
    o'zgartirgan qarorlar, ``case_type`` va uz/ru/en qidiruv teglari beriladi
    (``vmq778_tags.py``).

Hujjatdan hech qanday shaxsga oid ma'lumot olinmaydi (normativ hujjat, anketalar
bo'sh namuna). Ishga tushirish:

    python src/ingest_vmq778.py [manba.doc]
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from vmq778_tags import CASE_TYPES, TAGS, tags_for  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "vmq778_17.09.2019.doc"
OUT = ROOT / "data" / "vmq778_full.json"

SOURCE_URL = "https://lex.uz/docs/-4517458"
ADOPTED = "2019-09-18"  # Qonun hujjatlari ma'lumotlari milliy bazasi, 18.09.2019

_BLOCKS = {
    "ACT_TEXT", "BY_DEFAULT", "CHANGES_ORIGINS", "APPL_BANNER_LANDSCAPE_TITLE",
    "TEXT_HEADER_DEFAULT", "ACT_FORM", "ACT_TITLE_APPL", "FOOTNOTE", "PUBLICATION_ORIGIN",
}
_SUP = {"1": "¹", "2": "²", "3": "³", "4": "⁴"}
_MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7,
    "avgust": 8, "sentabr": 9, "oktabr": 10, "noyabr": 11, "dekabr": 12,
}
# "14. Matn" | "6 1 . Matn" (lex.uz ustki indeksni bo'sh joy bilan ajratadi)
_CLAUSE = re.compile(r"^(\d{1,2})(?: (\d))? ?\. (.*)$", re.S)
# Izoh qaysi bandga tegishli: "(2-bandning ...", "(6 1 -band ...", "(10 1 va 10 2 -bandlar",
# "(6-bobning nomi", "(3a-ilova ..."
_NOTE_REF = re.compile(
    r"^\((\d{1,2}[abvg]?)(?: (\d))?(?: va (\d{1,2})(?: (\d))?)? ?-"
    r"(bandning|bandlar|band|bobning|ilova)"
)
_ANNEX = re.compile(r"nizomga (\d[abvg]?)-ILOVA", re.I)
_HISTORICAL_DECISION = {
    # qaror 2-band: 2019-yilgi o'tish davri sanalari; 3, 5-band: bir oylik topshiriqlar
    "2": "2019-yil noyabr-dekabr o'tish davri qoidasi (amalda tugagan)",
    "3": "bir martalik, bir oy muddatli topshiriq (bajarilgan)",
    "5": "bir martalik, bir oy muddatli topshiriq (bajarilgan)",
}


# 1-ilova jadvalidagi GSMA inglizcha nomlari manbada buzilgan (lex.uz): tuzatiladi
_LABEL_FIXES = [
    (r"SMARTPNO N E", "SMARTPHONE"), (r"PNONE", "PHONE"), (r"NA N DNELD", "HANDHELD"),
    (r"VENICLE", "VEHICLE"), (r"DO N GLE", "DONGLE"), (r"CO NN ECTED", "CONNECTED"),
    (r"\( ", "("), (r" \)", ")"),
]


def _fix_label(text):
    for pat, rep_ in _LABEL_FIXES:
        text = re.sub(pat, rep_, text)
    return text


def _clean(text):
    text = text.replace("‎", " ").replace("\xa0", " ")
    text = re.sub(r"_{2,}", " ", text)
    return " ".join(text.split())


def _blocks(path):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for el in soup.find_all(class_=True):
        cls = el.get("class")[0]
        if cls not in _BLOCKS:
            continue
        if el.find_parent(class_=lambda c: c is not None and c in _BLOCKS):
            continue
        yield cls, el


def _date(day, month, year):
    return f"{int(year):04d}-{_MONTHS[month]:02d}-{int(day):02d}"


def parse_note(text):
    """Bitta lex.uz tahrir izohidan: qaysi band, qaysi qaror, qachondan kuchda."""
    m = _NOTE_REF.match(text)
    refs, kind_of_ref = [], None
    if m:
        kind_of_ref = m.group(5)
        refs.append(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
        if m.group(3):
            refs.append(m.group(3) + ("." + m.group(4) if m.group(4) else ""))
    decree = re.search(r"(\d{4})-yil (\d{1,2})-(\w+?)dagi (\d+)-son", text)
    effective = re.search(r"(\d{4})-yil (\d{1,2})-(\w+?)dan kuchga kiradi", text) or re.search(
        r"Kuchga kirish sanasi — (\d{4})-yil (\d{1,2})-(\w+)", text
    )
    published = re.search(r"(\d{2})\.(\d{2})\.(\d{4})-y\.", text)
    if effective:
        y, d, mo = effective.groups()
        valid_from = _date(d, mo.rstrip(")."), y)
    elif published:
        d, mo, y = published.groups()
        valid_from = f"{y}-{mo}-{d}"
    else:
        valid_from = None
    if "kuchini yoʻqotgan" in text or "chiqariladi" in text or "chiqarilgan" in text:
        change = "chiqarilgan"
    elif "kiritilgan" in text:
        change = "kiritilgan"
    elif "toʻldirilgan" in text:
        change = "toʻldirilgan"
    else:
        change = "tahrir"
    return {
        "refs": refs,
        "ref_kind": kind_of_ref,
        "decree": (f"VMQ {decree.group(4)}-son, {_date(decree.group(2), decree.group(3), decree.group(1))}"
                   if decree else None),
        "valid_from": valid_from,
        "change": change,
        "text": text,
    }


def _definition_split(paras):
    """2-band paragraflarini ta'riflarga ajratadi: har ta'rif + uning davomi."""
    defs, cur = [], None
    for p in paras[1:]:  # paras[0] = "2. Ushbu Nizomda quyidagi asosiy tushunchalardan..."
        head, sep, _ = p.partition(" — ")
        is_term = bool(sep) and len(head.split()) <= 20 and not (
            "(" in head and ")" not in head)
        if is_term:
            cur = {"term": head.strip(), "paras": [p]}
            defs.append(cur)
        elif cur is not None:
            cur["paras"].append(p)
    return paras[0], defs


def _term_key(term):
    t = term.split("(")[0].strip().lower()
    return re.sub(r"[^a-z0-9ʻʼ' -]", "", t).strip()


def parse(path=SOURCE):
    part = "qaror"
    chapter = None
    annex = None
    clauses = []  # (part, chapter, num, sup, paras)
    annex_blocks = {}  # annex id -> {"title": [...], "body": [...], "footnotes": [...]}
    notes = []
    publication = None
    for cls, el in _blocks(path):
        text = _clean(el.get_text(" ", strip=True))
        if not text:
            continue
        if cls == "APPL_BANNER_LANDSCAPE_TITLE":
            m = _ANNEX.search(text)
            if m:
                part, annex = "ilova", m.group(1)
                annex_blocks[annex] = {"title": [], "body": [], "footnotes": [], "table": None}
            else:
                part = "nizom"
            continue
        if cls == "PUBLICATION_ORIGIN":
            publication = text
            continue
        if cls == "CHANGES_ORIGINS":
            note = parse_note(text)
            note["context"] = {"part": part, "annex": annex,
                               "clause": clauses[-1][2] if clauses else None}
            notes.append(note)
            continue
        if part == "ilova":
            blk = annex_blocks[annex]
            if cls in ("ACT_TITLE_APPL", "ACT_FORM"):
                blk["title"].append(text)
            elif cls == "FOOTNOTE":
                blk["footnotes"].append(text)
            elif cls == "BY_DEFAULT":
                table = el if el.name == "table" else el.find("table")
                if table is not None:
                    blk["table"] = [
                        [_clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
                        for tr in table.find_all("tr")
                    ]
                blk["body"].append(text)
            continue
        if cls == "TEXT_HEADER_DEFAULT":
            chapter = text
            continue
        if cls != "ACT_TEXT":
            continue
        m = _CLAUSE.match(text)
        if m:
            clauses.append([part, chapter, m.group(1), m.group(2), [m.group(3).strip()]])
        elif clauses:
            clauses[-1][4].append(text)
    return clauses, annex_blocks, notes, publication


def _display(num, sup):
    return num + (_SUP.get(sup, sup) if sup else "")


def build_units(path=SOURCE):
    clauses, annexes, notes, publication = parse(path)

    # tahrir izohlarini band kalitiga bog'lash
    notes_by_key = {}
    for n in notes:
        if n["refs"]:
            prefix = {"ilova": "ilova", "bobning": "bob"}.get(n["ref_kind"], None)
            part = n["context"]["part"]
            for ref in n["refs"]:
                if prefix == "ilova":
                    key = f"ilova:{ref}"
                elif prefix == "bob":
                    key = f"bob:{ref}"
                else:
                    key = f"{'qaror' if part == 'qaror' else 'nizom'}:{ref}"
                notes_by_key.setdefault(key, []).append(n)
        else:
            notes_by_key.setdefault("umumiy", []).append(n)

    def amendments(key):
        return [n for n in notes_by_key.get(key, [])]

    def valid_from(key):
        dates = [n["valid_from"] for n in amendments(key) if n["valid_from"]
                 and n["change"] != "chiqarilgan"]
        return max(dates) if dates else ADOPTED

    def decrees(key):
        return sorted({n["decree"] for n in amendments(key) if n["decree"]})

    units = []

    def add(key, *, part, chapter, clause, display, title, text, temporal="current",
            historical_reason=None, case_type=None, extra_tags=(), paragraphs=None):
        units.append({
            "paragraphs": paragraphs or [text],
            "key": key,
            "part": part,
            "chapter": chapter,
            "clause": clause,
            "clause_display": display,
            "title": title,
            "text": text,
            "temporal_status": temporal,
            "historical_reason": historical_reason,
            "case_type": case_type or CASE_TYPES.get(key, "royxatdan_otkazish"),
            "tags": tags_for(key) + list(extra_tags),
            "valid_from": valid_from(key),
            "amended_by": decrees(key),
        })

    for part, chapter, num, sup, paras in clauses:
        clause = num + (f".{sup}" if sup else "")
        disp = _display(num, sup)
        key = f"{part}:{clause}"
        if part == "qaror":
            reason = _HISTORICAL_DECISION.get(clause)
            add(key, part="qaror", chapter=None, clause=clause, display=disp,
                title=f"VMQ 778-son qarori, {disp}-band",
                text=f"{disp}. " + "\n".join(paras),
                temporal="historical" if reason else "current", historical_reason=reason,
                paragraphs=[f"{disp}. {paras[0]}", *paras[1:]])
            continue
        if clause == "2":
            intro, defs = _definition_split(paras)
            for d in defs:
                term = d["term"]
                dkey = f"nizom:2:{_term_key(term)}"
                add(dkey, part="nizom", chapter=chapter, clause="2", display="2",
                    title=f"VMQ 778-son Nizomi, 2-band. Asosiy tushuncha: {term.split('(')[0].strip()}",
                    text="\n".join(d["paras"]), paragraphs=d["paras"],
                    case_type=CASE_TYPES.get(dkey, "royxatdan_otkazish"))
                # ta'rif ham 2-band tahrirlariga bog'liq
                units[-1]["valid_from"] = valid_from("nizom:2")
                units[-1]["amended_by"] = decrees("nizom:2")
            continue
        add(key, part="nizom", chapter=chapter, clause=clause, display=disp,
            title=f"VMQ 778-son Nizomi, {disp}-band" + (f" ({chapter})" if chapter else ""),
            text=f"{disp}. " + "\n".join(paras),
            paragraphs=[f"{disp}. {paras[0]}", *paras[1:]])

    # chiqarilgan (kuchini yo'qotgan) bandlar — faqat tarixiy izoh sifatida bo'ladi
    # ilovalar
    for aid, blk in annexes.items():
        title = " ".join(blk["title"]) or f"{aid}-ilova"
        key = f"ilova:{aid}"
        base_title = f"VMQ 778-son Nizomiga {aid}-ilova"
        if aid == "1" and blk["table"]:
            group = None
            rows = []
            for row in blk["table"][1:]:
                if len(row) >= 3 and row[2]:
                    group = row[2]
                name = _fix_label(re.sub(r"\s+", " ", row[1])) if len(row) > 1 else ""
                num = row[0].replace(" ", "")
                rows.append((num, name, group))
            for num, name, grp in rows:
                rkey = f"ilova:1:{num.rstrip('.')}"
                add(rkey, part="ilova", chapter=None, clause="1-ilova", display="1-ilova",
                    title=f"{base_title}. Qurilma turi: {name}",
                    text=f"1-ilova ({title}), {num} {name}. Roʻyxatga olish jarayoni: {grp}.",
                    case_type="royxatdan_otkazish")
                units[-1]["valid_from"] = valid_from(key)
            groups = {}
            for n, nm, g in rows:
                groups.setdefault(g, []).append(f"{n} {nm}")
            listing = "\n".join(f"{g}: " + "; ".join(items) for g, items in groups.items())
            add(key, part="ilova", chapter=None, clause="1-ilova", display="1-ilova",
                title=f"{base_title}. {title}",
                text=f"{title}:\n{listing}")
            continue
        if aid == "6" and blk["table"]:
            lines = []
            current = None
            for row in blk["table"][1:]:
                if row and re.match(r"^\d+\.$", row[0]):
                    current = row[1]
                    amount = row[2] if len(row) > 2 else ""
                    note = row[3] if len(row) > 3 else ""
                else:
                    amount = row[0] if row else ""
                    note = row[1] if len(row) > 1 else ""
                if not amount:
                    amount = "manbada miqdor koʻrsatilmagan"
                lines.append(f"{current}: {amount}" + (f" ({note})" if note else ""))
            text = (f"{title} (bitta IMEI-kod uchun):\n" + "\n".join(lines) + "\n"
                    + " ".join(blk["footnotes"]))
            add(key, part="ilova", chapter=None, clause="6-ilova", display="6-ilova",
                title=f"{base_title}. {title}", text=text, case_type="tolov_tarif")
            units[-1]["tariff"] = {
                "unit": "BHM (bazaviy hisoblash miqdori) foizi, bitta IMEI-kod uchun",
                "effective_from": valid_from(key),
                "amended_by": decrees(key),
                "requires_current_verification": True,
                "note": "BHM qiymati alohida belgilanadi va vaqt bilan o'zgaradi; "
                        "so'mdagi summa amaldagi BHM bo'yicha hisoblanadi.",
            }
            continue
        if not blk["body"]:  # 2- va 4-ilova: sxema (lex.uz'da rasm, matn yo'q)
            ref = {"2": "11-band", "4": "25-band"}.get(aid, "")
            add(key, part="ilova", chapter=None, clause=f"{aid}-ilova", display=f"{aid}-ilova",
                title=f"{base_title}. {title}",
                text=(f"{aid}-ilova — {title}. Sxema manbada rasm koʻrinishida berilgan "
                      f"(matnli tavsif yoʻq). Tartibning matnli asosi: Nizomning {ref}."))
            continue
        body = " ".join(blk["body"])
        body = re.sub(r"\s*\((imzo|toʻldirilgan sana|MOʻ)\)", "", body)
        add(key, part="ilova", chapter=None, clause=f"{aid}-ilova", display=f"{aid}-ilova",
            title=f"{base_title}. Anketa namunasi",
            text=(f"{aid}-ilova — anketa namunasi (shakl maydonlari). {body} "
                  "Eslatma: bu boʻsh namuna shakl; anketa Tizim operatori/roʻyxatga "
                  "oluvchiga topshiriladi, chatda shaxsiy maʼlumot yuborish talab qilinmaydi."))

    # tarixiy izohlar: har bir band bo'yicha bitta guruh-chunk
    hist = []
    for key, items in sorted(notes_by_key.items()):
        disp = key.split(":", 1)[-1]
        disp = re.sub(r"(\d+)\.(\d)", lambda m: m.group(1) + _SUP.get(m.group(2), m.group(2)), disp)
        label = {"qaror": "qarorining", "nizom": "Nizomining", "ilova": "Nizomiga",
                 "bob": "Nizomining", "umumiy": ""}[key.split(":", 1)[0]]
        what = {"ilova": f"{disp}-ilova", "bob": f"{disp}-bob"}.get(key.split(":", 1)[0],
                                                                   f"{disp}-band")
        removed = all(n["change"] == "chiqarilgan" for n in items)
        partly = not removed and any(n["change"] == "chiqarilgan" for n in items)
        lines = [f"- {n['text'].strip('() ')}" for n in items]
        hist.append({
            "key": f"tarix:{key}",
            "target": key,
            "title": f"VMQ 778-son {label} {what} — tahrirlar tarixi".replace("  ", " "),
            "text": (f"VMQ 778-son {label} {what} qachon va qaysi qaror bilan oʻzgartirilgan "
                     f"(tarixiy izoh, amaldagi qoida emas):\n" + "\n".join(lines)
                     + ("\nBu qism amaldagi tahrirda chiqarilgan/oʻz kuchini yoʻqotgan."
                        if removed else "")
                     + ("\nAyrim xatboshilar amaldagi tahrirda chiqarilgan." if partly else "")),
            "temporal_status": "historical_note",
            "removed": removed,
            "decrees": sorted({n["decree"] for n in items if n["decree"]}),
            "dates": sorted({n["valid_from"] for n in items if n["valid_from"]}),
            "tags": tags_for(f"tarix:{key}") + sorted(
                {d.split(",")[0].replace("VMQ ", "") for n in items if (d := n["decree"])}
                | {d.split(", ")[1][:4] + "-yil" for n in items if (d := n["decree"])}
                | {v[:4] + "-yil" for n in items if (v := n["valid_from"])}),
        })

    return {
        "document": "VMQ 778-son, 17.09.2019 — Oʻzbekiston Respublikasi hududida "
                    "foydalanilayotgan, sotish yoki shaxsiy foydalanish uchun olib "
                    "kiriladigan va ishlab chiqariladigan mobil qurilmalarni roʻyxatga "
                    "olish tartibi toʻgʻrisidagi nizom",
        "source_url": SOURCE_URL,
        "adopted": ADOPTED,
        "consolidated_through": max(n["valid_from"] for n in notes if n["valid_from"]),
        "publication_origin": publication,
        "units": units,
        "historical_notes": hist,
        "stats": {
            "units": len(units),
            "historical_notes": len(hist),
            "raw_change_notes": len(notes),
            "current_units": sum(1 for u in units if u["temporal_status"] == "current"),
            "historical_units": sum(1 for u in units if u["temporal_status"] == "historical"),
        },
    }


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    data = build_units(src)
    unknown = [k for k in TAGS if not any(
        u["key"] == k for u in data["units"]) and not any(
        h["key"] == k for h in data["historical_notes"])]
    if unknown:
        print("ogohlantirish: tegi bor, lekin birlik topilmadi:", unknown, file=sys.stderr)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(data["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
