# Asoslar: FastAPI, Endpoint, .env va HTTP (shu loyiha misolida)

> Bu qo'llanma checklistning **5-qadami** uchun. Mavhum nazariya emas — hammasi
> shu loyihangizdagi real fayllar bilan tushuntirilgan. O'qib chiqing, keyin
> "Sinab ko'ring" qismlarini bajaring.

---

## 1. HTTP so'rovi nima?

Internetда ikki dastur bir-biri bilan **so'rov (request)** va **javob (response)**
orqali gaplashadi. Har so'rovда:

- **Metod** — nima qilmoqchisiz: `GET` (ma'lumot olish), `POST` (ma'lumot yuborish).
- **URL / yo'l (path)** — qayerga: masalan `/api/v1/chat`.
- **Header** — qo'shimcha ma'lumot: masalan `Content-Type: application/json`.
- **Body (tana)** — yuborilayotgan ma'lumot (odatda JSON).

Javobda:
- **Status kod** — `200` (muvaffaqiyat), `429` (juda ko'p so'rov), `404` (topilmadi), `500` (server xatosi).
- **Body** — natija (JSON).

**Sizning loyihangizда** brauzer/Telegram → so'rov yuboradi → FastAPI backend → javob qaytaradi.

---

## 2. FastAPI nima?

FastAPI — Python'да **web API** yozish uchun kutubxona. Siz funksiya yozasiz,
FastAPI uni URL manziliga bog'laydi, JSON'ni avtomatik tekshiradi va hujjat
(Swagger) yaratadi.

Loyihangizда ilova [`app/main.py`](../app/main.py) dagi `create_app()` funksiyasida quriladi:
kalitlar (settings) o'qiladi, bilimlar bazasi yuklanadi, route'lar ulanadi.

---

## 3. Endpoint (route) nima?

**Endpoint** — bitta URL + metod uchun ishlaydigan funksiya. Sizning asosiy
endpointingiz [`app/api/routes/chat.py`](../app/api/routes/chat.py):

```python
router = APIRouter(prefix="/api/v1", tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse | JSONResponse:
    assistant = cast(AssistantService, request.app.state.assistant)
    response = await assistant.chat(payload, request.state.request_id)
    ...
    return response
```

Buni bo'lak-bo'lak tushunamiz:

| Qism | Ma'nosi |
|---|---|
| `@router.post("/chat")` | `POST /api/v1/chat` manziliga kelgan so'rovni shu funksiya bajaradi (`prefix` + `/chat`) |
| `payload: ChatRequest` | Kelgan JSON avtomatik `ChatRequest`ga aylantiriladi va **tekshiriladi** |
| `response_model=ChatResponse` | Javob ham qat'iy `ChatResponse` shaklида qaytadi |
| `async def` | Bir vaqtda ko'p so'rovni samarali bajarish uchun |

**So'rov/javob shakli** [`app/domain/schemas.py`](../app/domain/schemas.py) da (`ChatRequest`, `ChatResponse`).
`ChatRequest` maydonlari: `session_id`, `language`, `message`. Agar `message` bo'sh
bo'lsa yoki 4000 belgidan oshsa — FastAPI avtomatik `422` xato qaytaradi.

Boshqa endpointlar: `GET /health` ([health.py](../app/api/routes/health.py)),
`/api/v1/complaints/...` ([complaints.py](../app/api/routes/complaints.py)).

---

## 4. `.env` va sozlamalar (Settings)

`.env` — **maxfiy va muhitga bog'liq** qiymatlarni kodдан tashqarida saqlaydigan
fayl (API kalit, limitlar, provayder tanlash). U **hech qachon GitHub'ga
qo'yilmaydi** (`.gitignore`да).

Kod uni [`app/core/config.py`](../app/core/config.py) dagi `Settings` orqali o'qiydi:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", ...)
    llm_provider: str = Field(default="mock", ...)   # .env dagi LLM_PROVIDER
    llm_api_key: SecretStr | None = ...              # .env dagi LLM_API_KEY
    request_rate_limit_per_minute: int = Field(default=20, ...)
```

Ya'ni `.env`да `LLM_PROVIDER=openai` yozsangiz, kodда `settings.llm_provider`
avtomatik `"openai"` bo'ladi. Kalit `SecretStr` — bosib chiqarilганда yashiriladi
(xavfsizlik).

**API key nima uchun?** OpenAI'ga "men to'lov qiluvchi mijozman" deb tanitish uchun.
Har so'rovда `Authorization: Bearer sk-...` headeri bilan yuboriladi. Sizning
kodингизда buni [`app/providers/openai_responses.py`](../app/providers/openai_responses.py) hal qiladi — kalit `.env`дан keladi.

---

## 5. Hammasi birga qanday ishlaydi

```
Foydalanuvchi savol yozadi
        │  POST /api/v1/chat   { "language": "uz", "message": "IMEI ..." }
        ▼
FastAPI  →  ChatRequest ga tekshiradi
        ▼
AssistantService.chat()
   ├─ kategoriyani aniqlaydi (imei / mnp / ...)
   ├─ bilimlar bazasidan tasdiqlangan manba qidiradi
   ├─ manba bo'lsa → LLM (OpenAI) grounded javob yozadi
   └─ bo'lmasa → operatorga yo'naltiradi
        ▼
ChatResponse (JSON)  →  foydalanuvchiga
```

---

## 6. Sinab ko'ring (amaliyot)

1. **Serverни ishga tushiring** (VS Code → Run and Debug → "Run AI Assistant server", yoki):
   ```bash
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
   ```

2. **Swagger'ni oching** — bu barcha endpointlarni ko'rsatadigan interaktiv hujjat:
   <http://127.0.0.1:8000/docs> → `POST /api/v1/chat` → "Try it out" → JSON yuboring.

3. **Terminaldan HTTP so'rov** (yangi terminalда):
   ```bash
   curl -s -X POST http://127.0.0.1:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"language\":\"uz\",\"message\":\"IMEI raqamni qanday tekshirish mumkin?\"}"
   ```
   Javobда `response_type`, `grounded`, `sources` maydonlarini kuzating.

4. **`.env` bilan tajriba:** `LLM_PROVIDER=mock` qilib serverni qayta ishga tushiring —
   javob tarmoqсиз, tez keladi. `openai` qilsangiz — real, sekinroq. Farqini his qiling.

---

## 7. Keyingi o'qish uchun tushunchalar

- **REST API** — URL + metod orqali resurslar bilan ishlash uslubi.
- **JSON** — ma'lumot almashish formati (`{"kalit": "qiymat"}`).
- **Pydantic** — FastAPI ishlatadigan tekshirish kutubxonasi (`ChatRequest` shu).
- **async/await** — bir vaqtda ko'p so'rovni bloklamasdan bajarish.
- **Status kodlar** — 2xx (ok), 4xx (mijoz xatosi), 5xx (server xatosi).

> Ushbu qo'llamani o'qib, 6-bo'limдаги amaliyotni bajarsangiz, 5-qadam bajarilgan
> hisoblanadi. Keyingi qadam — web chat oynasi (6–8).
