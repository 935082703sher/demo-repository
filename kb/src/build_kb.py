# -*- coding: utf-8 -*-
"""
Yakuniy bilim bazasini yig'adi:
  out/kb.jsonl        — RAG uchun to'liq korpus (barcha qatlamlar)
  out/qa.jsonl        — faqat savol-javob juftliklari
  out/kb_stats.json   — statistika
  out/kb.md           — inson o'qishi uchun ko'rinish
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from faq_data import FAQ                     # noqa: E402
from legal_data import LAW, REGULATIONS      # noqa: E402
from mask import find_leaks                  # noqa: E402
from normalize import detect_lang, normalize  # noqa: E402
from vmq778_data import VMQ778               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

# Chunk hajmi: embedding modeli (bge-m3 / multilingual-e5) uchun optimal
MAX_CHARS = 1200
OVERLAP = 150


def rid(prefix, text):
    return f"{prefix}-{hashlib.sha1(text.encode()).hexdigest()[:16]}"


def split_long(text, max_chars=MAX_CHARS, overlap=OVERLAP):
    """Uzun matnni jumla chegarasida bo'ladi."""
    if len(text) <= max_chars:
        return [text]
    parts, cur = [], ""
    for sent in text.replace("\n", " ").split(". "):
        sent = sent.strip()
        if not sent:
            continue
        if len(cur) + len(sent) + 2 > max_chars and cur:
            parts.append(cur.strip())
            cur = cur[-overlap:] + " "
        cur += sent + ". "
    if cur.strip():
        parts.append(cur.strip())
    return parts


def base(**kw):
    t = kw["text"]
    kw.setdefault("lang", detect_lang(t))
    kw.setdefault("text_norm", normalize((kw.get("title") or "") + " " + t))
    kw.setdefault("pii_masked", True)
    kw.setdefault("pii_hits", {})
    kw.setdefault("n_tokens", max(1, len(t) // 3))
    kw.setdefault("valid_from", None)
    return kw


def build():
    rows = []

    # --- 1-qatlam: qonun (authority 1) ---------------------------------------
    for a in LAW:
        for j, part in enumerate(split_long(a["text"])):
            rows.append(base(
                id=rid("law", a["art"] + str(j)),
                doc_id=f"orq-445-{a['art']}",
                source_type="qonun",
                source_title="ЎРҚ-445 «Jismoniy va yuridik shaxslarning murojaatlari to‘g‘risida»gi Qonun (yangi tahrir)",
                title=f"{a['art']}. {a['title']}",
                authority=1,
                domain="murojaat_tartibi",
                case_type="boshqa",
                outcome=None,
                text=part,
                legal_refs=[f"ЎРҚ-445 {a['art']}"],
                tags=a["tags"],
                valid_from="2017-09-11",
            ))

    # --- 2-qatlam: normativ hujjatlar (authority 2) ---------------------------
    for r in REGULATIONS:
        rows.append(base(
            id=rid("reg", r["ref"]),
            doc_id=r["ref"],
            source_type="nizom",
            source_title=r["ref"],
            title=r["title"],
            authority=2,
            domain="imei",
            case_type="royxatdan_otkazish",
            outcome=None,
            text=r["text"],
            legal_refs=[r["ref"]],
            tags=[],
        ))

    # --- 2-qatlam (davomi): VMQ 778-son muhim qoidalari (authority 2) --------
    for r in VMQ778:
        rows.append(base(
            id=rid("reg778", r["title"]),
            doc_id="VMQ 778-son",
            source_type="nizom",
            source_title="VMQ 778-son, 17.09.2019",
            title=r["title"],
            authority=2,
            domain=r.get("domain", "imei"),
            case_type=r.get("case_type", "royxatdan_otkazish"),
            outcome=None,
            text=r["text"],
            legal_refs=["VMQ 778-son"],
            tags=r.get("tags", []),
        ))

    # --- 3-qatlam: FAQ (authority 3) -----------------------------------------
    qa_rows = []
    for f in FAQ:
        text = f"Savol: {f['q']}\nJavob: {f['a']}"
        row = base(
            id=rid("faq", f["q"]),
            doc_id="faq-mnp-imei",
            source_type="faq",
            source_title="MNP va IMEI FAQ (O‘zTTBRM)",
            title=f["q"],
            authority=3,
            domain=f["domain"],
            case_type=f["case"],
            outcome=None,
            text=text,
            legal_refs=f["refs"],
            tags=f["alt"],
            text_norm=normalize(" ".join([f["q"]] + f["alt"] + [f["a"]])),
        )
        rows.append(row)
        qa_rows.append({
            "id": row["id"], "domain": f["domain"], "case_type": f["case"],
            "question": f["q"], "alt_questions": f["alt"], "answer": f["a"],
            "refs": f["refs"], "source": "MNP va IMEI FAQ (O‘zTTBRM)",
        })

    # --- 4-qatlam: amaliyot (javob xatlari, authority 4) ---------------------
    letters_path = OUT / "letters.jsonl"
    n_letters = 0
    if letters_path.exists():
        for line in letters_path.open(encoding="utf-8"):
            r = json.loads(line)
            # Mazmunsiz xatlar (faqat "bog'lanib tushuntirildi") — past qiymat
            r["tags"] = []
            r["title"] = None
            r["has_substance"] = len(r["text"]) > 900 and r["domain"] != "boshqa"
            n_letters += 1
            parts = split_long(r["text"])
            for k, p in enumerate(parts):
                rr = dict(r)
                rr["text"] = p
                rr["text_norm"] = normalize(p)
                rr["n_tokens"] = max(1, len(p) // 3)
                if len(parts) > 1:
                    rr["id"] = f"{r['id']}-p{k}"
                    rr["part"] = f"{k+1}/{len(parts)}"
                rows.append(rr)

    # --- yozish ---------------------------------------------------------------
    OUT.mkdir(exist_ok=True)
    with (OUT / "kb.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (OUT / "qa.jsonl").open("w", encoding="utf-8") as f:
        for r in qa_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # --- sifat nazorati -------------------------------------------------------
    leaks = {r["id"]: find_leaks(r["text"]) for r in rows if find_leaks(r["text"])}

    stats = {
        "jami_chunk": len(rows),
        "qatlamlar": dict(Counter(r["source_type"] for r in rows)),
        "authority": dict(Counter(r["authority"] for r in rows)),
        "domain": dict(Counter(r["domain"] for r in rows)),
        "case_type": dict(Counter(r["case_type"] for r in rows)),
        "lang": dict(Counter(r["lang"] for r in rows)),
        "qa_juftlik": len(qa_rows),
        "javob_xatlari": n_letters,
        "mazmunli_xatlar": sum(1 for r in rows if r.get("has_substance")),
        "ortacha_uzunlik": sum(len(r["text"]) for r in rows) // max(1, len(rows)),
        "eng_uzun_chunk": max(len(r["text"]) for r in rows),
        "pii_leak_soni": len(leaks),
        "pii_leak_namuna": {k: v for k, v in list(leaks.items())[:5]},
    }
    (OUT / "kb_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- markdown ko'rinish ---------------------------------------------------
    md = ["# RTMC AI asistent — bilim bazasi\n",
          f"Jami chunk: **{len(rows)}** · Q&A: **{len(qa_rows)}** · "
          f"Javob xatlari: **{n_letters}** · PII leak: **{len(leaks)}**\n"]
    for lvl, name in [(1, "1. Qonun (ЎРҚ-445)"), (2, "2. Normativ hujjatlar"),
                      (3, "3. FAQ"), (4, "4. Amaliyot — javob xatlari (namuna)")]:
        md.append(f"\n## {name}\n")
        sel = [r for r in rows if r["authority"] == lvl]
        for r in sel[:60 if lvl < 4 else 5]:
            md.append(f"### {r.get('title') or r['doc_id']}\n")
            md.append(r["text"][:1500] + ("…\n" if len(r["text"]) > 1500 else "\n"))
        if lvl == 4 and len(sel) > 5:
            md.append(f"\n_… va yana {len(sel)-5} ta xat `out/kb.jsonl` faylida._\n")
    (OUT / "kb.md").write_text("\n".join(md), encoding="utf-8")

    return stats


if __name__ == "__main__":
    s = build()
    print(json.dumps(s, ensure_ascii=False, indent=2))
