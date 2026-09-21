# RTMC AI Assistant — To'liq Roadmap (MVP yo'l xaritasi)

> Sana: 2026-09-21 · Asos: `AI asistant.pptx` (RTMC.UZ Enterprise AI Assistant) va
> hozirgi kod bazasi (Demo 1 → Demo 2 → Demo 3 Stage 3C).
>
> Maqsad: IMEI va MNP standart murojaatlarini Web va Telegram orqali 24/7
> AI self-service kanaliga o'tkazuvchi ishlaydigan MVP tayyorlash.

---

## 1. Hozir qayerdamiz? (Current state)

Kod bazasi allaqachon **jiddiy backend poydevorига** ega. Slaydlardagi arxitektura
zanjiri `Web/Telegram → PII Guard → Diagnostic Engine → KB + RAG → LLM → Tasdiqlangan yechim`
bo'yicha holat:

| Slayddagi komponent | Holat | Kodda qayerda |
|---|---|---|
| IMEI / MNP kategoriyalari | ✅ Bor | `app/domain/enums.py` (`Category`) |
| PII Guard (maskalash) | ✅ Bor | `app/services/pii.py`, `privacy_scan.py`, `secure_values.py` |
| KB + RAG (grounding) | ✅ Bor (sintetik) | `app/services/knowledge.py`, `grounding.py`, `app/data/approved_faq.demo.json` |
| Guardrails (input/scope/output/citation) | ✅ Bor | `app/services/guardrails.py`, `scope.py` |
| LLM provayder chegarasi (mock/OpenAI/Ollama) | ✅ Bor | `app/providers/` (`mock_llm`, `openai_responses`, `ollama`) |
| Ko'p tillilik (uz/ru/en) | ✅ Bor | `app/i18n/` |
| Operatorga eskalatsiya (human handoff) | ✅ Bor | `app/services/human_handoff.py` |
| Complaint (shikoyat) workflow + governance | ✅ Bor | `app/services/complaint_*`, `governed_complaint_orchestrator.py` |
| Usage/rate limit, sessiyalar, idempotency | ✅ Bor | `app/services/usage_limits.py`, `repositories/` |
| FastAPI API (`/api/v1/chat`, complaints, health) | ✅ Bor | `app/api/routes/` |
| Testlar (26 fayl) + 60-keys eval suite | ✅ Bor | `tests/`, `evaluations/` |
| Docker / Compose / Makefile | ✅ Bor | `Dockerfile`, `compose.yaml`, `Makefile` |

**Hozirgi chat oqimi** (`app/services/assistant.py`): xabar → kategoriya aniqlash →
kerakli maydonlar yetishmasa follow-up savol → KB qidiruv → grounded javob yoki handoff.

### Nima yetishmayapti (slaydlarga nisbatan)

| Bo'shliq | Holat | Ta'sir |
|---|---|---|
| **Telegram kanali** | ❌ Umuman yo'q | Slaydda kanal sifatida ko'rsatilgan (Web + Telegram) |
| **Diagnostic Engine (IMEI/MNP)** | ⚠️ Zaif | Follow-up savollar umumiy shikoyat-yig'ish uchun (`applicant_type`, `region`...). Slaydlardagi *"2–5 diagnostik savol → sabab → qadamma-qadam yechim → natijani tekshirish"* troubleshooting oqimi yo'q. **Bu loyihaning asosiy qiymati.** |
| **Real IMEI/MNP bilim bazasi** | ⚠️ Faqat sintetik | Har kategoriyada 3 ta demo yozuv. Real diagnostik ssenariylar/yechimlar kerak |
| **Web chat frontend** | ⚠️ Stub | `index.html` faqat "Welcome..." matni; real chat widjeti yo'q |
| **Secure Form (rasmiy murojaatda PII)** | ❌ Yo'q | Slaydda: PII faqat Secure Form orqali kiritiladi |
| **KPI metrikalari** | ❌ Yo'q | Self-Service Resolution Rate, Call Deflection Rate, Cost per Resolved Case |
| **Kuzatuv (observability) / analitika** | ❌ Yo'q | Pilotda real tejashni o'lchash uchun (slaydda ta'kidlangan) |

**Bir jumlada:** Backend "skeleti" 70% tayyor, lekin loyihaning **asosiy farqlovchi qiymati
(diagnostika oqimi) va ikkinchi kanal (Telegram) hamda foydalanuvchi interfeysi** hali yo'q.

---

## 2. Maqsad (Target — slaydlardan)

- **Doira (MVP):** faqat IMEI va MNP standart murojaatlari.
- **Kanallar:** Web-sayt + Telegram, 24/7.
- **Oqim:** Muammo → Diagnostika (2–5 savol) → Ehtimoliy sabab → Tasdiqlangan yechim →
  Qadamma-qadam ko'rsatma → Natijani tekshirish → hal bo'lmasa operatorga.
- **Tamoyil:** AI qoidalarni o'ylab topmaydi — haqiqat manbai = kompaniyaning
  tasdiqlangan Knowledge Base'i. LLM faqat tabiiy til qatlami.
- **Xavfsizlik:** PII maskalash (JShShIR, passport/ID, telefon, karta, OTP, parol);
  rasmiy PII faqat Secure Form orqali; MVP'da IMEI/MNP bazalarига Direct DB Access yo'q.
- **Infratuzilma:** MVP = API (bulutli LLM API). On-Prem keyingi bosqichda qayta baholanadi.
- **Muvaffaqiyat (KPI):** Self-Service Resolution Rate, Call Deflection Rate,
  Cost per Resolved Case.

---

## 3. Roadmap — bosqichma-bosqich

Har bosqich mustaqil "yetkazib beriladigan qiymat"ga ega. Taxminiy mehnat baholari
1 muhandis uchun; slaydlardagi "3 oyda ishlaydigan tizim" doirasiga sig'adi.

### Bosqich 0 — Poydevorni mustahkamlash (≈3–5 kun)
**Maqsad:** mavjud tizimni ishonchli ishga tushirib, o'lchov nuqtasini belgilash.
- [ ] Lokal ishga tushirish: `make check`, `python -m evaluations.run`, `make run` — hammasi yashil.
- [ ] `.env` konfiguratsiyasini hujjatlashtirish; `LLM_PROVIDER` variantlarini sinash (mock/ollama).
- [ ] Joriy eval natijalarini "baseline" sifatida saqlash (`evaluations/reports/`).
- **Natija:** ishlaydigan backend + o'lchanadigan boshlang'ich holat.

### Bosqich 1 — Diagnostic Engine (IMEI/MNP) 🎯 *asosiy qiymat* (≈2–3 hafta)
**Maqsad:** slaydlardagi troubleshooting oqimini qurish.
- [ ] Diagnostika model/kontrakti: `DiagnosticFlow`, `DiagnosticStep`, `ProbableCause`, `ResolutionStep`.
- [ ] IMEI uchun qaror daraxti (masalan: "ro'yxatdan o'tmayapti" → savollar → sabablar → yechim).
- [ ] MNP uchun qaror daraxti (masalan: ko'chirish rad etildi / kechikdi → savollar → yechim).
- [ ] `assistant.py` oqimiga diagnostik holatlarni qo'shish (`ConversationState`ga
      `DIAGNOSTIC_*` bosqichlari), 2–5 savol chegarasi, natijani tekshirish qadami.
- [ ] Har yechim tasdiqlangan KB manbasiga bog'lanishi (citation majburiy) — AI o'ylab topmasin.
- [ ] Testlar: har ssenariy uchun determinized oqim testi.
- **Natija:** IMEI/MNP bo'yicha real o'z-o'ziga xizmat ko'rsatish (matn interfeysida).

### Bosqich 2 — Real Knowledge Base (IMEI/MNP kontenti) (≈1–2 hafta, biznes bilan parallel)
**Maqsad:** sintetik demo yozuvlarini tasdiqlangan real kontent bilan almashtirish.
- [ ] IMEI/MNP bo'yicha eng ko'p uchraydigan murojaatlarni tasniflash (209 murojaat tahlili asosida).
- [ ] Har biriga: savol → diagnostika → sabab → tasdiqlangan yechim (uz/ru/en) kontenti.
- [ ] KB governance jarayoni orqali kiritish (`knowledge_governance.py`, tasdiqlash izlari).
- **Natija:** amaliy foydalanishga yaroqli bilim bazasi. *(Kontent RTMC mutaxassislaridan.)*

### Bosqich 3 — Web chat frontend (≈1–1.5 hafta)
**Maqsad:** foydalanuvchi ko'radigan chat interfeysi.
- [ ] Chat widjeti: til tanlash, xabarlar oqimi, diagnostik savol/javob, yechim ko'rsatish, operatorga tugma.
- [ ] Mavjud `/api/v1/chat` API bilan integratsiya, CORS allaqachon sozlangan.
- [ ] Saytga o'rnatiluvchi (embeddable) variant.
- **Natija:** Web kanali ishlaydi.

### Bosqich 4 — Telegram bot kanali (≈1 hafta)
**Maqsad:** ikkinchi kanal.
- [ ] Telegram bot adapteri (webhook yoki long-polling), xabarlarni `/api/v1/chat`ga uzatish.
- [ ] Sessiya/til holatini Telegram chat_id bilan bog'lash.
- [ ] Tugmalar (inline keyboard) orqali diagnostik variantlar.
- **Natija:** Web + Telegram — slaydlardagi ikkala kanal.

### Bosqich 5 — Secure Form + rasmiy murojaat chegarasi (≈3–5 kun)
**Maqsad:** PII xavfsizligini slaydlarga muvofiqlashtirish.
- [ ] Rasmiy murojaatда PII faqat alohida Secure Form orqali (chat oqimida emas).
- [ ] Chatda PII aniqlanganda → maskalash + Secure Formga yo'naltirish.
- **Natija:** slaydlardagi xavfsizlik tamoyili to'liq bajarilgan.

### Bosqich 6 — KPI, analitika va pilotga tayyorlik (≈1 hafta)
**Maqsad:** slaydlardagi 3 KPI'ni o'lchash.
- [ ] Har suhbat natijasini belgilash: hal bo'ldi / operatorga o'tdi / tashlab ketildi.
- [ ] Metrikalar: Self-Service Resolution Rate, Call Deflection Rate, Cost per Resolved Case.
- [ ] Oddiy dashboard yoki hisobot eksporti; LLM xarajat/latency o'lchovi (allaqachon qisman bor).
- **Natija:** pilotda real tejashni o'lchash imkoniyati.

### Keyingi bosqich (MVP'dan tashqari)
- On-Premise LLM baholash (real trafik, xarajat, xavfsizlik asosida).
- Direct DB Access (IMEI/MNP) — faqat tegishli ruxsat va xavfsizlik ko'rigidan keyin.
- Qo'shimcha kategoriyalar (network_quality, number_codes, ...).

---

## 4. Tavsiya etilgan tartib

```
Bosqich 0 (poydevor)
        └─> Bosqich 1 (Diagnostic Engine) ◀── eng katta qiymat, birinchi
                    ├─> Bosqich 2 (real KB, biznes bilan parallel)
                    ├─> Bosqich 3 (Web frontend)
                    └─> Bosqich 4 (Telegram)
                                └─> Bosqich 5 (Secure Form)
                                            └─> Bosqich 6 (KPI + pilot)
```

Bosqich 1 → 3 → 4 ketma-ketligida allaqachon Bosqich 1 oxirida "ishlaydigan demo" bo'ladi.

---

## 5. Asosiy qarorlar / risklar

- **LLM provayder:** MVP uchun API (mock bilan test, keyin haqiqiy API kaliti — RTMC ruxsati bilan).
  Slayddagi xarajat: ≈$4 (1k suhbat) → ≈$400 (100k suhbat).
- **Kontent bog'liqligi:** Bosqich 2 (real KB) RTMC mutaxassislaridan tasdiqlangan
  kontent talab qiladi — bu texnik emas, tashkiliy bog'liqlik.
- **Xavfsizlik:** MVP'da hech qanday real fuqaro ma'lumoti saqlanmaydi; Direct DB Access yo'q.
- **"3 oy" doirasi:** Bosqich 0–6 ≈ 8–10 hafta (1 muhandis) — kontent tayyor bo'lsa, mos keladi.

---

## 6. Keyingi qadam (darhol boshlash mumkin)

1. **Bosqich 0**'ni yopamiz: tizimni lokal ishga tushirib, `make check` + eval yashil ekanini tasdiqlaymiz.
2. So'ng **Bosqich 1 (Diagnostic Engine)** dizaynini kontrakt fayllaridan boshlaymiz.

> Ushbu roadmap kod bazasi holatiga bog'liq — komponentlar o'zgarsa yangilab boriladi.
