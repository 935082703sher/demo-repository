# RTMC AI Assistant — Amalga oshirish checklisti

> Bu checklist foydalanuvchining ish ketma-ketligi bo'yicha tuzilgan.
> Belgilar: ✅ bajarildi · 👉 navbatdagi qadam · ⬜ kutilmoqda · 📚 o'rganish
> Har qadam yakunlanганда `[ ]` → `[x]` qiling.
> Batafsil reja: [ROADMAP.md](ROADMAP.md)

---

## A bosqich — Muhit va backend (poydevor)

- [x] **1. Python va loyiha muhitini o'rnatish** ✅
  - `demo-repository/.venv` (Python 3.13), `pip install -e '.[dev]'` bajarilgan.
- [x] **2. Mavjud testlarni ishga tushirish va backend ishlashini tekshirish** ✅
  - Natija: **297 passed, 4 skipped** (Windows POSIX testlari skip).
  - `/health` va `/api/v1/chat` javob beryapti; IMEI kategoriyasi to'g'ri aniqlanadi.

## B bosqich — OpenAI bilan tanishuv

- [ ] **3. OpenAI API key yaratish va lokal `.env`ga qo'yish** 👉 *keyingi qadam (siz qilasiz)*
  - `.env` tayyor. platform.openai.com'dan key olib, `.env`da:
    `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4o-mini`, `LLM_API_KEY=sk-...`
- [ ] **4. OpenAI bilan faqat sintetik test savollarini yuborib ko'rish** ⬜
  - Haqiqiy fuqaro ma'lumotisiz, sintetik savollar bilan sinash.
- [ ] **5. FastAPI, API endpoint, `.env`, API key va HTTP request asoslarini o'rganish** 📚

## C bosqich — Web chat interfeysi

- [ ] **6. Saytga oddiy chat oynasi qo'shish** ⬜
- [ ] **7. Chat oynasini `POST /api/v1/chat` endpoint'iga ulash** ⬜
- [ ] **8. Saytda assistant javobi, manbalar (sources), xato va "operator kerak" holatlarini ko'rsatish** ⬜

## D bosqich — Bilim bazasi va sifat

- [ ] **9. Haqiqiy, tekshirilgan tashkilot ma'lumotlarini knowledge bazaga qo'shish** ⬜
  - RTMC mutaxassislaridan tasdiqlangan IMEI/MNP kontenti kerak (tashkiliy bog'liqlik).
- [ ] **10. RAG, prompt, citation va hallucination nima ekanini o'rganish** 📚
- [ ] **11. OpenAI orqali javob sifati, tezlik va xarajatni baholash** ⬜

## E bosqich — Lokal model (Ollama)

- [ ] **12. Ollama'ni lokal kompyuter yoki ichki serverga o'rnatish** ⬜ (kod tayyor: `docs/LOCAL_LLM.md`)
- [ ] **13. Lokal modelni yuklash va `LLM_PROVIDER=ollama`ga o'tish** ⬜
- [ ] **14. OpenAI va Ollama natijalarini bir xil savollar bilan solishtirish** ⬜
- [ ] **15. Eng mos lokal modelni tanlash va ichki serverga joylashtirish** ⬜

## F bosqich — Ma'lumotlar bazasi va xavfsizlik

- [ ] **16. PostgreSQL qo'shish** ⬜
  - session, chat limit, draft va audit ma'lumotlari uchun (hozir in-memory).
- [ ] **17. Login/API himoya, rate limit, secret manager va HTTPS sozlash** ⬜
  - rate limit qisman bor (`app/services/usage_limits.py`); qolganlari kerak.

## G bosqich — Deploy va kuzatuv

- [ ] **18. Docker orqali sayt backendini serverga deploy qilish** ⬜ (Dockerfile/compose bor)
- [ ] **19. Monitoring, loglar, testlar va backup qo'shish** ⬜

## Yon yo'nalish (ixtiyoriy)

- [ ] **20. Dify'ni alohida o'rganish** 📚
  - prompt, RAG va model sinovlari uchun. **Hozircha asosiy sayt backendining o'rniga qo'ymaslik.**

---

### Umumiy holat
- Bajarildi: **2 / 20**
- Navbatda: **3-qadam — OpenAI API key + `.env`**
