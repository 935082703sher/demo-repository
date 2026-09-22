# RTMC AI asistent — bilim bazasi (knowledge base)

Murojaatlar bo'limi uchun RAG bilim bazasini tayyorlash quvuri (pipeline).
Manba: O'zTTBRM murojaatlariga javob xatlari, MNP/IMEI FAQ, ЎРҚ-445 Qonuni va
tegishli VMQ nizomlari.

---

## 1. Asosiy g'oya: 4 qatlamli bilim bazasi

Javob xatlari — bilim emas, **amaliyot namunasi**. Haqiqiy bilim normativ
hujjatlarda. Shuning uchun korpus `authority` (ishonch darajasi) bo'yicha
qatlamlarga bo'linadi va retrieval'da yuqori qatlam ustunlik qiladi:

| authority | Qatlam | Nima uchun | Hozirgi hajm |
|---|---|---|---|
| **1** | Qonun — ЎРҚ-445 (muddatlar, javob talablari, anonim murojaat, maxfiylik) | Yagona haqiqiy huquqiy asos | 11 chunk |
| **2** | Normativ hujjatlar — VMQ 778, 463, 828; DBQ 526; PQ 3512; 1-sonli Nizom | Soha qoidalari | 6 chunk |
| **3** | FAQ (IMEI + MNP) — tasdiqlangan savol-javob | Foydalanuvchi savollariga to'g'ridan-to'g'ri javob | 32 Q&A |
| **4** | Amaliyot — anonimlashtirilgan javob xatlari | Uslub, tipik kazuslar, qaysi normaga havola qilinadi | 178 xat → 282 chunk |

**Muhim qoida:** asistent 4-qatlamdan faqat *uslub va kazus namunasi* sifatida
foydalanadi, faktni esa 1–3-qatlamdan oladi. Prompt'da shu aniq yozilishi kerak,
aks holda model eski tariflarni yoki bekor qilingan normani takrorlaydi.

---

## 2. Quvur (pipeline)

```
manba hujjatlar (.docx/.doc/.pdf)
        │
        ▼  ingest_sources.py      matn ajratish (python-docx / pdfplumber / libreoffice)
     raw/*.txt
        │
        ▼  build_letters.py       xatlarga ajratish → PII maskalash → tasniflash
   out/letters.jsonl
        │
        ▼  build_kb.py            4 qatlamni birlashtirish → chunking → JSONL
   out/kb.jsonl · out/qa.jsonl · out/kb.md · out/kb_stats.json
        │
        ▼  eval_retrieval.py      sifat nazorati (recall@5, PII leak)
```

### Ishga tushirish

```bash
pip install python-docx pdfplumber
python3 src/ingest_sources.py /yo'l/hujjatlar_papkasi   # barcha .docx/.doc/.pdf
python3 src/build_letters.py
python3 src/build_kb.py
python3 src/eval_retrieval.py
```

---

## 3. PII maskalash (`src/mask.py`)

Murojaat matnlari — shaxsiy ma'lumot. ЎРҚ-445 19-moddasi ularni oshkor etishni
taqiqlaydi, shuning uchun maskalash majburiy, **ichki foydalanishda ham**.

Maskalanadi: FIO, telefon, IMEI, pasport seriya-raqami, JSHSHIR/PINFL, bank
kartasi, e-mail, murojaat raqami (DOCNO), yashash manzili.

Ikki muhim yechim:

1. **Turg'un pseudonim.** Bir xil qiymat har doim bir xil tokenga aylanadi
   (`[PHONE_0AFB0E]`), shuning uchun matnning ichki bog'lanishi saqlanadi, lekin
   shaxsni tiklab bo'lmaydi (sha1 + salt, qaytarib bo'lmaydigan).
2. **Whitelist.** Normativ raqamlar (`778-son`, `ЎРҚ-445`), qisqa raqamlar
   (`*#06#`, `*1170#`, `1170`), tariflar (`82 400`) va UZIMEI ofis manzili
   maskalanmaydi — bular foydali bilim.

Nazorat: `find_leaks()` maskalashdan keyin qolib ketgan telefon/IMEI/pasport/
e-mail'ni qidiradi. **Hozirgi natija: 0 ta leak** (331 chunk bo'yicha).

> Diqqat: manba faylda ba'zi telefonlar allaqachon `(91)******-01` shaklida
> qisman maskalangan, ba'zilari esa **umuman maskalanmagan** (masalan
> `(90) 607-71-11`). Ya'ni qo'lda maskalash ishonchsiz — shuning uchun avtomatik
> bosqich kerak.

---

## 4. Taksonomiya (`src/taxonomy.py`)

Har bir chunk uch o'lchovda belgilanadi:

- **domain** — `imei` · `mnp` · `murojaat_tartibi` · `aloqa_sifati` · `boshqa`
- **case_type** — `klon_imei` · `aniqlanmagan_imei` · `bojxona` ·
  `royxatdan_otkazish` · `tolov_tarif` · `blokdan_chiqarish` · `eski_qurilma` ·
  `esim_ikkinchi_slot` · `yoqotilgan_ogirlangan` · `mnp_ariza_rad` ·
  `mnp_tartib` · `taklif` · `shikoyat`
- **outcome** (faqat xatlar) — `ijobiy_hal` · `tushuntirish` · `etiroz_yoq` ·
  `muammo_yoq` · `boglanib_bolmadi` · `rad`

Bu metadata retrieval'da filtr sifatida ishlatiladi: masalan foydalanuvchi klon
IMEI haqida so'rasa, `case_type=klon_imei` bo'yicha qattiq filtr qo'yiladi va
noto'g'ri kazus chiqmaydi.

---

## 5. Uch tillilik

Korpus asosan o'zbek lotin yozuvida. Uch til qo'llab-quvvatlanadi:

- **`text_norm`** — har bir chunk uchun kirill→lotin translitеratsiya +
  apostrofsizlashtirish + lowercase. Foydalanuvchi kirillda yozsa ham BM25
  lotin hujjatni topadi.
- **`tags` / `alt`** — FAQ va Qonun yozuvlarida ruscha va kirillcha muqobil
  formulalar. Bu leksik qidiruvdagi bo'shliqni yopadi.
- **Embedding** — **bge-m3** yoki **multilingual-e5-large** tavsiya etiladi:
  ikkalasi ham uz-lat, uz-cyr va rus tilini bitta fazoda joylashtiradi,
  shuning uchun tarjima kerak emas.

Sinov natijasi (`eval_retrieval.py`, faqat BM25, embedding'siz):
**recall@5 = 15/15 (100%)**, shu jumladan 5 ta ruscha/kirillcha savol.
Ruscha savollar dastlab 2 ta MISS bergan edi — `alt` aliaslar qo'shilgach
tuzatildi. Bu leksik qidiruvning chegarasini ko'rsatadi: **ishlab chiqarishda
hybrid (BM25 + embedding) majburiy**.

---

## 6. Chunking

- Maksimal 1200 belgi, 150 belgi overlap, jumla chegarasida bo'linadi.
- Qonun moddalari va FAQ yozuvlari — **bitta chunk = bitta mazmuniy birlik**
  (modda / savol-javob). Bu eng muhim qaror: ularni mexanik bo'lish javob
  sifatini keskin tushiradi.
- Xatlarda standart boilerplate ("...Sud organlariga murojaat qilish huquqiga
  egasiz") tasniflashdan oldin olib tashlanadi — aks holda deyarli har bir xat
  "shikoyat" deb tasniflanardi.

---

## 7. Chiqish formati

`out/kb.jsonl` — har satr bitta chunk:

```json
{
  "id": "faq-3f2a…", "doc_id": "faq-mnp-imei",
  "source_type": "faq", "source_title": "MNP va IMEI FAQ (O‘zTTBRM)",
  "authority": 3, "domain": "imei", "case_type": "tolov_tarif",
  "outcome": null, "lang": "uz_latn",
  "title": "IMEI-kodni ro‘yxatdan o‘tkazish qancha turadi?",
  "text": "Savol: … Javob: …",
  "text_norm": "savol imei kodni royxatdan otkazish …",
  "legal_refs": ["VMQ 778-son"], "tags": ["IMEI narxi", "стоимость …"],
  "valid_from": null, "pii_masked": true, "pii_hits": {}, "n_tokens": 210
}
```

`out/qa.jsonl` — faqat savol-javob juftliklari (fine-tuning yoki FAQ-bot uchun).

---

## 8. Vektor bazaga yuklash

```python
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
import json

model = SentenceTransformer("BAAI/bge-m3")
rows = [json.loads(l) for l in open("out/kb.jsonl", encoding="utf-8")]
vecs = model.encode([r["text"] for r in rows], normalize_embeddings=True)

cli = QdrantClient(url="http://localhost:6333")
cli.recreate_collection(
    "rtmc_kb",
    vectors_config=models.VectorParams(size=vecs.shape[1],
                                       distance=models.Distance.COSINE))
cli.upsert("rtmc_kb", points=[
    models.PointStruct(id=i, vector=v.tolist(), payload=r)
    for i, (v, r) in enumerate(zip(vecs, rows))])
```

Qidiruvda: `authority` bo'yicha boost (1→×1.5, 4→×0.7), `domain`/`case_type`
bo'yicha filtr, `has_substance=false` xatlarni chiqarib tashlash.

---

## 9. Asistent prompt'i uchun qoidalar

1. Faktni faqat `authority ≤ 3` manbalardan ol; `authority=4` — uslub namunasi.
2. Har bir javobda `legal_refs` dagi normaga havola qil (ЎРҚ-445 27-modda talabi:
   javob asoslari qonunchilik normalariga havola bilan berilishi kerak).
3. Bilim bazasida javob yo'q bo'lsa — to'qima. "Bu masala bo'yicha aniq ma'lumot
   yo'q, murojaatni rasmiy tartibda yuboring" deb operator/forma'ga yo'naltir.
4. Foydalanuvchi tilida javob ber (ЎРҚ-445 27-modda: javob murojaat etilgan
   tilda bo'lishi kerak).
5. Shaxsiy ma'lumot so'ralsa yoki berilsa — saqlama, javobda takrorlama.

---

## 10. Keyingi qadamlar

- [ ] `.doc` va PDF manbalarini `ingest_sources.py` bilan qo'shish
      (11 ta PDF skan bo'lsa — `tesseract-ocr` + `uzb`/`rus` til paketi kerak)
- [ ] VMQ 778/463/828 nizomlarining **to'liq matnini** qo'shish — hozir faqat
      xatlarda havola qilingan bandlar bor
- [ ] Tariflarga `valid_from` / `valid_to` qo'shish (2025-08-01 dan amalda) va
      eskirgan normalarni `deprecated` deb belgilash
- [ ] 50–100 ta real savoldan gold test to'plami, recall@5 va answer-accuracy
      o'lchash
- [ ] Har chorakda qayta yig'ish (ЎРҚ-445 35-moddasi chorakda umumlashtirishni
      talab qiladi — shu jarayonga ulash mantiqiy)
