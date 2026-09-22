# -*- coding: utf-8 -*-
"""
Bilim bazasi sifatini tekshirish: leksik (BM25) qidiruv orqali test savollariga
to'g'ri chunk qaytarilishini o'lchaydi. Kirill va rus tilidagi savollar
`normalize()` orqali lotinga keltirilgani uchun lotin korpusdan topiladi.

Bu — sanity check. Ishlab chiqarishda hybrid (BM25 + bge-m3 embedding) tavsiya etiladi.
"""
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from normalize import normalize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def tok(s):
    return re.findall(r"[a-z0-9]{3,}", normalize(s))


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [tok(d) for d in docs]
        self.k1, self.b = k1, b
        self.N = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(1, self.N)
        self.df = Counter()
        for d in self.docs:
            self.df.update(set(d))
        self.tf = [Counter(d) for d in self.docs]

    def score(self, q):
        qs = tok(q)
        out = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i]) or 1
            s = 0.0
            for t in qs:
                if t not in tf:
                    continue
                idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * tf[t] * (self.k1 + 1) / (
                    tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


TESTS = [
    ("IMEI kodni qanday bilsam bo'ladi?", ["*#06#"]),
    ("IMEI ro'yxatdan o'tkazish necha kun?", ["30 kalendar", "60 kalendar"]),
    ("IMEI ro'yxatga olish narxi qancha?", ["82 400", "103 000"]),
    ("Telefonim bloklandi nima qilay?", ["blokdan", "ro‘yxatdan o‘tkaz"]),
    ("Klonlangan IMEI ro'yxatga olinadimi?", ["klonlangan", "qora ro‘yxat"]),
    ("Raqamni boshqa operatorga ko'chirmoqchiman", ["MNP", "ko‘chir"]),
    ("MNP arizam rad etildi nega?", ["qarzdorlik", "rad etil"]),
    ("Murojaat necha kunda ko'rib chiqiladi?", ["15 kun", "bir oy"]),
    ("Anonim murojaat ko'rib chiqiladimi?", ["anonim"]),
    # kirill
    ("IMEI кодини қандай билиш мумкин?", ["*#06#"]),
    ("Рақамни бошқа операторга кўчириш", ["ko‘chir", "MNP"]),
    # rus
    ("Как узнать IMEI телефона?", ["*#06#"]),
    ("Сколько стоит регистрация IMEI?", ["82 400"]),
    ("Перенос номера к другому оператору", ["MNP", "ko‘chir"]),
    ("Срок рассмотрения обращения", ["15 kun", "bir oy"]),
]


def main():
    rows = [json.loads(l) for l in (ROOT / "out" / "kb.jsonl").open(encoding="utf-8")]
    corpus = [(r.get("title") or "") + " " + " ".join(r.get("tags") or []) + " " + r["text"]
              for r in rows]
    bm = BM25(corpus)

    ok = 0
    print(f"{'savol':<48} {'top-1 manba':<28} hit")
    print("-" * 92)
    for q, expect in TESTS:
        sc = bm.score(q)
        order = sorted(range(len(sc)), key=lambda i: -sc[i])[:5]
        top5 = " ".join(rows[i]["text"] for i in order)
        hit = any(e.lower() in top5.lower() for e in expect)
        ok += hit
        t1 = rows[order[0]]
        label = f"{t1['source_type']}/{t1['domain']}"
        print(f"{q[:46]:<48} {label:<28} {'OK' if hit else 'MISS'}")
    print("-" * 92)
    print(f"recall@5 = {ok}/{len(TESTS)} = {ok/len(TESTS):.0%}")
    return ok, len(TESTS)


if __name__ == "__main__":
    main()
