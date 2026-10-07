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
import re
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
# VMQ 778 to'liq korpusida band xatboshilari shu hajmgacha bitta chunkga yig'iladi
VMQ_PART_CHARS = 900
VMQ778_FULL = ROOT / "data" / "vmq778_full.json"
MNP3275_FULL = ROOT / "data" / "mnp_3275_full.json"


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


def _group_paragraphs(paras, limit=VMQ_PART_CHARS):
    """Band xatboshilarini mazmunini buzmasdan ~limit hajmli qismlarga yig'adi."""
    parts, cur = [], []
    for p in paras:
        if cur and len("\n".join(cur)) + len(p) + 1 > limit:
            parts.append("\n".join(cur))
            cur = []
        cur.append(p)
    if cur:
        parts.append("\n".join(cur))
    out = []
    for part in parts:  # bitta xatboshining o'zi juda uzun bo'lsa — jumla chegarasida
        out.extend(split_long(part, max_chars=MAX_CHARS))
    return out


def vmq778_full_rows(path=VMQ778_FULL):
    """VMQ 778-son to'liq korpusi: amaldagi matn (authority 2) + tahrir tarixi (authority 5).

    Amaldagi konsolidatsiyalangan matn — faol huquqiy bilim (temporal_status=current);
    2019-yilgi o'tish davri qoidalari — historical; lex.uz tahrir izohlari —
    historical_note. Retriever historical qatlamni faqat tarixiy savollarda
    oldinga chiqaradi, aks holda amaldagi band ustun turadi.
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for u in data["units"]:
        parts = _group_paragraphs(u["paragraphs"])
        if u["temporal_status"] == "historical":
            # the model sees only the passage, so the passage itself says it is history
            marker = f"[Tarixiy qoida — amaldagi tartib emas: {u['historical_reason']}]\n"
            parts = [marker + p for p in parts]
        for i, text in enumerate(parts):
            title = u["title"] + (f" — {i + 1}/{len(parts)}-qism" if len(parts) > 1 else "")
            row = base(
                id=rid("vmq778full", f"{u['key']}#{i}"),
                doc_id=f"kb-vmq778:{u['key']}",
                source_type="nizom_toliq",
                source_title=data["document"],
                title=title,
                authority=2,
                domain="imei",
                case_type=u["case_type"],
                outcome=None,
                text=text,
                legal_refs=[f"VMQ 778-son, {u['clause_display']}"
                            + ("" if "ilova" in u["clause_display"] else "-band")],
                tags=u["tags"],
                valid_from=u["valid_from"],
                temporal_status=u["temporal_status"],
                lang="uz_latn",
            )
            row["amended_by"] = u["amended_by"]
            row["clause"] = u["clause_display"]
            if u.get("historical_reason"):
                row["historical_reason"] = u["historical_reason"]
            if u.get("tariff"):
                row["tariff"] = u["tariff"]
            if len(parts) > 1:
                row["part"] = f"{i + 1}/{len(parts)}"
            rows.append(row)
    for h in data["historical_notes"]:
        head, *lines = h["text"].split("\n")
        parts = _group_paragraphs(lines)
        for i, body in enumerate(parts):
            rows.append(base(
                id=rid("vmq778note", f"{h['key']}#{i}"),
                doc_id=f"kb-vmq778:{h['key']}",
                source_type="nizom_tarixiy_izoh",
                source_title=data["document"] + " — tahrirlar tarixi",
                title=h["title"] + (f" — {i + 1}/{len(parts)}-qism" if len(parts) > 1 else ""),
                authority=5,
                domain="imei",
                case_type="boshqa",
                outcome=None,
                text=head + "\n" + body,
                legal_refs=h["decrees"],
                tags=h["tags"],
                valid_from=max(h["dates"]) if h["dates"] else None,
                temporal_status="historical_note",
                lang="uz_latn",
            ))
    return rows


def mnp3275_rows(path=MNP3275_FULL):
    """3275-son Qoidalarning MNP korpusi (domain=mnp).

    * amaldagi normativ bandlar — source_type=mnp_nizom_current, authority 2;
      har chunk avval oddiy tildagi izoh, keyin bandning o'zgarmagan matni;
    * rad etish sabablari bo'yicha qo'llanma (belgi / sabab / yechim / normativ
      asos) — source_type=mnp_rejection_guide, authority 3;
    * tahrir izohlari — source_type=mnp_nizom_historical_note, authority 5.
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    title = data["document"]
    rows = []
    for u in data["units"]:
        parts = _group_paragraphs(u["paragraphs"])
        for i, text in enumerate(parts):
            body = (u["plain"] + "\nNormativ matn: " + text) if u["plain"] else text
            row = base(
                id=rid("mnp3275", f"{u['key']}#{i}"),
                doc_id=f"kb-mnp3275:{u['key']}",
                source_type="mnp_nizom_current",
                source_title=title,
                title=u["title"] + (f" — {i + 1}/{len(parts)}-qism" if len(parts) > 1 else ""),
                authority=2,
                domain="mnp",
                case_type=u["case_type"],
                outcome=None,
                text=body,
                legal_refs=u["legal_refs"],
                tags=u["tags"],
                valid_from=u["valid_from"],
                temporal_status="current",
                lang="uz_latn",
            )
            row["requires_realtime_status"] = False
            row["amended_by"] = u["amended_by"]
            if u["excerpt"]:
                row["excerpt"] = True
            rows.append(row)
    for r in data["rejection_reasons"]:
        steps = " ".join(f"{i}) {s}" for i, s in enumerate(r["resolution"], 1))
        rows.append(base(
            id=rid("mnp3275rad", r["id"]),
            doc_id=f"kb-mnp3275:rad:{r['id']}",
            source_type="mnp_rejection_guide",
            source_title=title + " — rad etish sabablari",
            title=r["title"],
            authority=3,
            domain="mnp",
            case_type=r["case_type"],
            outcome=None,
            text=(f"{r['title']}.\nBelgisi: {r['symptom']}\nSababi: {r['cause']}\n"
                  f"Nima qilish kerak: {steps}\nNormativ asos: {', '.join(r['legal_refs'])}."),
            legal_refs=r["legal_refs"],
            tags=r["tags"],
            temporal_status="current",
            lang="uz_latn",
        ))
    for h in data["historical_notes"]:
        rows.append(base(
            id=rid("mnp3275note", h["key"]),
            doc_id=f"kb-mnp3275:{h['key']}",
            source_type="mnp_nizom_historical_note",
            source_title=title + " — tahrirlar tarixi",
            title=h["title"],
            authority=5,
            domain="mnp",
            case_type="mnp_tartib",
            outcome=None,
            text=h["text"],
            legal_refs=h["decrees"],
            tags=h["tags"],
            valid_from=max(h["dates"]) if h["dates"] else None,
            temporal_status="historical_note",
            lang="uz_latn",
        ))
    return rows


def build_rows():
    """Barcha qatlamlar bo'yicha chunklar (faylga yozmasdan; testlar ham shundan foydalanadi).

    Qaytaradi: (rows, qa_rows, n_letters).
    """
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
            temporal_status=r.get("temporal_status", "current"),
        ))

    # --- 2-qatlam (davomi): VMQ 778-son TO'LIQ korpusi (amaldagi + tarixiy) ---
    # Curated qoidalar (yuqorida) tez-tez so'raladigan savollar uchun qoladi; to'liq
    # korpus noodatiy va chuqur savollarga javob beradi.
    rows.extend(vmq778_full_rows())
    # (main'dagi "vmq778_full_source.txt" asosidagi yirik-chunkli qatlam shu
    # tuzilgan korpus bilan almashtirildi: aynan o'sha matn band raqamlari va
    # amaldagi/tarixiy ajratish bilan indekslanadi; txt fayl o'qish uchun qoladi.)

    # --- 2-qatlam (davomi): 3275-son Qoidalarning MNP korpusi ----------------
    # FAQ va toza KB maqolalari qisqa javob uchun qoladi; bu korpus chuqur va
    # noodatiy MNP savollariga normativ band raqami bilan javob beradi.
    rows.extend(mnp3275_rows())

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

    # --- 2-qatlam (davomi): UZIMEI mijozlar bilim bazasi (uzimei.uz) ----------
    # Rasmiy bosqichma-bosqich yo'riqnomalar (D01-D20), FAQ va ssenariylar; RAG
    # shu boy kontentdan grounded javob beradi.
    # (lang=None auto-detects; the English file forces lang="en" so English
    #  questions retrieve English content.)
    n_uzkb = 0
    for fname, force_lang in (("uzimei_knowledge.jsonl", None), ("uzimei_knowledge_en.jsonl", "en")):
        uzkb_path = ROOT / "data" / fname
        if not uzkb_path.exists():
            continue
        for line in uzkb_path.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            kw = dict(
                id=rid("uzkb", r["text"][:60] + str(n_uzkb)),
                doc_id="uzimei-bilim-bazasi",
                source_type="bilim_bazasi",
                source_title="UZIMEI mijozlar bilim bazasi (uzimei.uz), 25.09.2026",
                title=r.get("section", "UZIMEI bilim bazasi"),
                authority=2,
                domain=r.get("domain", "imei"),
                case_type="boshqa",
                outcome=None,
                text=r["text"],
                legal_refs=[],
                tags=[],
                valid_from="2026-09-25",
            )
            if force_lang:
                kw["lang"] = force_lang
            rows.append(base(**kw))
            n_uzkb += 1

    # --- 3-qatlam (davomi): tasdiqlangan yechim kartalari (authority 3) -------
    # Diagnostika daraxtlarining resolution card'lari: tasdiqlangan kontent, shu
    # bois RAG ular haqidagi ma'lumot savollariga ham javob bera oladi.
    cards_path = ROOT.parent / "app" / "data" / "diagnostics.json"
    n_cards = 0
    if cards_path.exists():
        for c in json.loads(cards_path.read_text(encoding="utf-8")).get("cards", []):
            cid = c["id"]
            domain = "imei" if cid.startswith("imei") else "mnp" if cid.startswith("mnp") else "boshqa"
            title = (c.get("title") or {}).get("uz") or cid
            cause = (c.get("probable_cause") or {}).get("uz", "")
            steps = [s.get("uz", "") for s in c.get("steps", [])]
            where = (c.get("where_to_apply") or {}).get("uz", "")
            parts = [title, cause]
            if steps:
                parts.append("Qadamlar: " + " ".join(f"{i}) {s}" for i, s in enumerate(steps, 1)))
            if where:
                parts.append("Murojaat: " + where)
            rows.append(base(
                id=rid("card", cid),
                doc_id=f"card-{cid}",
                source_type="qaror_karta",
                source_title="Tasdiqlangan yechim kartalari (O‘zTTBRM)",
                title=title,
                authority=3,
                domain=domain,
                case_type="boshqa",
                outcome=None,
                text="\n".join(p for p in parts if p),
                legal_refs=c.get("kb_refs", []),
                tags=[],
            ))
            n_cards += 1

    # --- 3-qatlam (davomi): toza bilim bazasi v1.0 maqolalari (authority 3) ---
    # Faqat retrieval_policy.index_statuses dagi (published_candidate) maqolalar
    # indekslanadi; amaldagi holati tekshirilishi kerak bo'lgan (tarif, muddat,
    # limit), ekspert kutayotgan va tarixiy maqolalar javob manbai bo'lmaydi.
    clean_kb_path = ROOT.parent / "app" / "data" / "knowledge_base.v1_0.json"
    n_clean = 0
    if clean_kb_path.exists():
        clean_kb = json.loads(clean_kb_path.read_text(encoding="utf-8"))
        allowed = set(clean_kb["retrieval_policy"]["index_statuses"])
        for art in clean_kb["articles"]:
            if art["status"] not in allowed or not art.get("answer"):
                continue
            steps = art.get("resolution_steps") or []
            parts = [art["title"], art["answer"]]
            if steps:
                parts.append("Qadamlar: " + " ".join(f"{i}) {s}" for i, s in enumerate(steps, 1)))
            rows.append(base(
                id=rid("kbv1", art["id"]),
                doc_id=art["id"],
                source_type="bilim_maqola",
                source_title=f"Toza bilim bazasi v{clean_kb['kb_version']}",
                title=art["title"],
                authority=3,
                domain=art["domain"],
                case_type="boshqa",
                outcome=None,
                text="\n".join(parts),
                legal_refs=[],
                tags=[],
            ))
            n_clean += 1

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

    ids = [r["id"] for r in rows]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"takrorlangan chunk id: {sorted(dupes)[:5]}")
    return rows, qa_rows, n_letters


def build():
    rows, qa_rows, n_letters = build_rows()

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
        "temporal_status": dict(Counter(r.get("temporal_status", "current") for r in rows)),
        "vmq778_full_chunks": sum(1 for r in rows if r["source_type"] == "nizom_toliq"),
        "vmq778_current_chunks": sum(1 for r in rows if r["source_type"] == "nizom_toliq"
                                     and r.get("temporal_status") == "current"),
        "vmq778_historical_chunks": sum(1 for r in rows if r["source_type"] == "nizom_toliq"
                                        and r.get("temporal_status") == "historical"),
        "vmq778_historical_notes": sum(1 for r in rows
                                       if r["source_type"] == "nizom_tarixiy_izoh"),
        "mnp_3275_current_chunks": sum(1 for r in rows
                                       if r["source_type"] == "mnp_nizom_current"),
        "mnp_3275_rejection_guides": sum(1 for r in rows
                                         if r["source_type"] == "mnp_rejection_guide"),
        "mnp_3275_historical_notes": sum(1 for r in rows
                                         if r["source_type"] == "mnp_nizom_historical_note"),
        "mnp_faq": sum(1 for r in rows if r["source_type"] == "faq" and r["domain"] == "mnp"),
        "mnp_case_types": sorted({r["case_type"] for r in rows if r["domain"] == "mnp"}),
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
                      (3, "3. FAQ"), (4, "4. Amaliyot — javob xatlari (namuna)"),
                      (5, "5. Tahrirlar tarixi (amaldagi qoida emas)")]:
        md.append(f"\n## {name}\n")
        sel = [r for r in rows if r["authority"] == lvl]
        for r in sel[:200 if lvl < 4 else 5]:
            md.append(f"### {r.get('title') or r['doc_id']}\n")
            md.append(r["text"][:1500] + ("…\n" if len(r["text"]) > 1500 else "\n"))
        if lvl == 4 and len(sel) > 5:
            md.append(f"\n_… va yana {len(sel)-5} ta xat `out/kb.jsonl` faylida._\n")
    (OUT / "kb.md").write_text("\n".join(md), encoding="utf-8")

    return stats


if __name__ == "__main__":
    s = build()
    print(json.dumps(s, ensure_ascii=False, indent=2))
