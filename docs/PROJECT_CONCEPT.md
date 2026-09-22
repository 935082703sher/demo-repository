# Loyiha konsepsiyasi — Mijoz murojaatlarini diagnostika qiladigan Enterprise AI Assistant

> Ushbu hujjat rahbariyat va texnik jamoa uchun. Maqsad — texnologiyани maqtash
> emas, balki **tizim qanday muammoni qanday hal qilishini** aniq tushuntirish.
> Texnik atamalar zarur joyдаgina ishlatilgan va soddaqilib izohlangan.

**Asosiy g'oya bir jumlada:** Biz chatbot yaratmayapmiz — biz mijoz muammosini
tushunadigan, diagnostika qiladigan, kompaniyaning **tasdiqlangan bilimlari**
asosida yechim beradigan va zarur holatда inson operatoriga to'g'ri
yo'naltiradigan Enterprise AI Assistant yaratmoqdamiz.

---

## 1. Loyihaning asosiy g'oyasi

Kompaniya mijozlariga **Web-sayt** va **Telegram bot** orqali 24/7 xizmat
ko'rsatadigan AI Assistant. Birinchi bosqichда tizim faqat ikki yo'nalishда
ishlaydi: **IMEI** (mobil qurilma identifikatorini ro'yxatga olish) va **MNP**
(raqamни boshqa operatorga ko'chirish).

Bu **oddiy FAQ chatbot emas.** Uning ishlash mantig'i — operator kabi:

```
Mijoz murojaatini tushunish
   ↓
Muammo kompaniya vakolatiga kirishini aniqlash
   ↓
Kerakli diagnostik savollarni berish
   ↓
Muammoning ehtimoliy sababini aniqlash
   ↓
Tasdiqlangan ma'lumotlardan yechim topish
   ↓
Bosqichma-bosqich nima qilishni tushuntirish
   ↓
Natijani tekshirish
   ↓
Hal bo'lmasa — operator yoki rasmiy murojaatga yo'naltirish
```

### Hayotiy misol: "IMEI ro'yxatdan o'tmayapti"

Mijoz yozadi: *"Telefonimning IMEI'si ro'yxatdan o'tmayapti."*

Oddiy chatbot darrov 10 ta ehtimoliy sababni to'kib solardi. Bizning Assistant
esa **operator kabi savol-javob orqali muammoni toraytiradi**:

1. **AI:** "Qurilmani O'zbekistonда sotib olganmisiz yoki chetdan olib kelinganmi?"
   → *Mijoz: "Chetdan."*
2. **AI:** "Bojsiz olib kirish me'yoridан (yarim yilda 1 ta qurilma) ortiq bo'lganmi?"
   → *Mijoz: "Ha, ikkinchisi."*
3. **AI (ehtimoliy sabab):** "Ehtimol, me'yordan ortiq qurilma uchun **bojxona
   kirim orderi** talab qilinadi."
4. **AI (yechim — Resolution Card):** "Quyidagilarni qiling: (1) bojxona kirim
   orderini oling; (2) uni Tizim operatoriga taqdim eting; (3) so'ng IMEI
   ro'yxatga olinadi. Rasmiy manba: VMQ 463-son. Sayt: www.uzimei.uz."
5. **AI (natijani tekshirish):** "Ro'yxatga olindi mi? Agar yo'q bo'lsa,
   operatorga yo'naltiraman."

Ya'ni AI **faktni o'zidан o'ylab topmadi** — tasdiqlangan qoidадан oldi va
mijozni qadamma-qadam yechimga olib bordi.

---

## 2. Muammo nimada?

Bugungi holatда mijozларга xizmat **qimmat va operatorларга bog'liq**:

| Ko'rsatkich | Qiymat |
|---|---|
| Operator xizmatlari xarajati | **200 mln so'm/oy** |
| Yillik xarajat | **2,4 mlrd so'm/yil** |
| Operator–mijoz muloqoti | **≈50 000 minut/oy** |
| Shartli o'rtacha xarajat | **≈4 000 so'm/minut** |

### Murojaatlar ikki alohida kanalда

Bu ikki raqamни **bitta statistika sifatida qo'shmaslik kerak** — ular boshqa-boshqa
kanallar va o'lchov usullari:

**A) Klassifikatsiyalangan murojaatlar** (yil boshidan 1-avgustgacha) — **209 ta**:
- IMEI — **124 ta**
- MNP — **48 ta**
- **IMEI + MNP = 172 ta = 82,3%** (barcha klassifikatsiyalangan murojaatларning)

**B) Qayta aloqa va sayt orqali kelgan alohida so'rovlar** — **2 978 ta**:
- IMEI — **2 512 ta**
- MNP — **466 ta**

### Nega loyiha kerak?

Har ikki kanalда ham **standart, takrorlanuvchi savollar** ustunlik qiladi.
Operatorlar vaqtining katta qismini bir xil IMEI/MNP savollariga sarflaydi — bu
qimmat (4 000 so'm/minut) va cheklangan (ish vaqti bilan). Bu savollarни
avtomatlashtirsak, operatorlar **murakkab holatларга** ko'proq vaqt ajratadi.

### Nega aynan IMEI va MNP'dан boshlash kerak?

- Klassifikatsiyalangan murojaatларning **82,3%** aynan shular.
- Digital kanalда ham **eng ko'p so'rov** (2 512 IMEI) shu yo'nalishда.
- Bu savollar **qoidага asoslangan** (muddat, to'lov, tartib) — ya'ni
  tasdiqlangan bilim bazasi bilan aniq javob berish mumkin.
- Ya'ni **eng katta hajm + eng aniq javob berish mumkin bo'lган soha** = eng
  yuqori samara. Katta ta'sir uchun to'g'ri boshlang'ich nuqta.

---

## 3. AI Assistant oddiy chatbotdan nima bilan farq qiladi?

**Oddiy chatbot:**
```
Savol → Tayyor javob
```
Kalit so'zга qarab oldindan yozilgan javobни qaytaradi. Kontекstни tushunmaydi,
diagnostika qilmaydi.

**Bizning AI Assistant:**
```
Muammo → Tushunish → Diagnostika → Sabab → Tasdiqlangan ma'lumot → Yechim → Natijани tekshirish
```

Eng muhim farq: Assistant foydalanuvchiga **birdaniga 10 ta ehtimoliy sababни
to'kib solmaydi.** U **operator kabi ketma-ket savollar** orqali muammoni
toraytirib boradi va faqat tegishli yechimni beradi.

---

## 4. Tizimning ishlash mantig'i (arxitektura)

```
Foydalanuvchi
   ↓
Web / Telegram          (kirish kanallari)
   ↓
PII Guard               (shaxsiy ma'lumotni maskalaydi)
   ↓
Scope & Intent          (murojaat vakolatga kiradimi? niyati nima?)
   ↓
Diagnostic Engine       (ketma-ket savollar — muammoni toraytirish)
   ↓
Knowledge Base + RAG    (tasdiqlangan faktни topish)
   ↓
LLM                     (tabiiy tilда tushunarli javob yozish)
   ↓
Resolution              (yechim — Resolution Card)
   ↓
Solved / Escalation / Appeal   (hal bo'ldi / operator / rasmiy murojaat)
```

Har bir komponent — **nima qiladi, nega kerak, bo'lmasa nima buziladi:**

| Komponent | Nima qiladi | Nega kerak | Bo'lmasa |
|---|---|---|---|
| **Web / Telegram** | Mijoz bilan aloqa nuqtalari | Mijoz o'zi qulay kanalда yozadi | Faqat bitta kanal — kamroq qamrov |
| **PII Guard** | JShShIR, telefon, karta va h.k. maskalaydi | Shaxsiy ma'lumot AI'ga/logга tushmasin | Maxfiylik buziladi, qonun buzilishi |
| **Scope & Intent** | Murojaat kompaniya vakolatiga kiradimi, niyati nima ekanini aniqlaydi | Begona/xavfli so'rovларни darrov ajratish | AI o'z sohasidan tashqariga javob berib, xato qiladi |
| **Diagnostic Engine** | Savol-javob bilan sababни toraytiradi | Operator mantig'i — aniq yechim uchun | Umumiy, foydasiz javoblar |
| **Knowledge Base + RAG** | Savolга mos tasdiqlangan faktни topadi | Fakt manbai — AI o'ylab topmasin | AI yolg'on tarif/muddat aytadi (hallucination) |
| **LLM** | Tabiiy tilда tushunarli javob yozadi | Inson tilida muloqot | Quruq, robotсimon javoblar |
| **Resolution** | Tayyor yechim kartаsini beradi | Bir xil muammoga bir xil to'g'ri yechim | Har safar boshqacha, ishonchsiz javob |
| **Escalation / Appeal** | Operator yoki rasmiy murojaatga o'tkazadi | AI hal qila olmasa — xavfsiz chiqish | Mijoz muammosi hал bo'lmay qoladi |

---

## 5. AI modelning roli

**AI model barcha qarorlarни mustaqil qabul qilmaydi.** U asosan:
- tabiiy tilni tushunish;
- o'zbek / rus / aralash tilni tushunish;
- foydalanuvchi niyatini aniqlash;
- tushunarli javob yaratish;
- dialogни davom ettirish;
- rasmiy murojaat matnini tayyorlash — uchun ishlatiladi.

**AI quyidagi faktларni o'zidan yaratmasligi kerak:** tarif, qonun, IMEI qoidasi,
MNP talabi, xizmat muddati, rasmiy kontakt. Bularning barchasi **faqat
tasdiqlangan bilim bazasidан** olinadi.

> **Asosiy prinsip:**
> **LLM — muloqot mexanizmi. Knowledge Base — faktlar manbai. Decision Tree —
> diagnostika va biznes mantiqi.**

---

## 6. Knowledge Base va RAG

**Knowledge Base (bilim bazasi)** — kompaniyaning **tasdiqlangan** ma'lumotlari:

**IMEI:** ro'yxatdan o'tkazish qoidalari · jarayonlar · muddatlar · to'lovlar ·
hujjatlar · keng tarqalgan muammolar · tasdiqlangan yechimlar · rasmiy linklar · kontaktlar.

**MNP:** raqam ko'chirish talablari · cheklovlar · jarayon · hujjatlar · keng
tarqalgan muammolar · yechimlar · rasmiy kontaktlar.

### RAG oddiy tilда

**RAG (Retrieval-Augmented Generation)** — "topib, keyin javob berish".
Ishlash tartibi:
1. Mijoz savol beradi.
2. Tizim bilim bazasidan **shu savolга eng mos tasdiqlangan bo'lakларни topadi**
   (masalan IMEI to'lovi haqidagi qoida).
3. Faqat **o'sha topilgan matnни** AI'ga beradi va: "faqat shu asosда javob ber,
   o'zingdан qo'shma" deydi.
4. AI o'sha faktларга asoslanib tushunarli javob yozadi va **manbaни** ko'rsatadi.

Natijada AI **faqat kompaniya tasdiqlagan ma'lumot bilan** javob beradi. Bilim
bazasi **doim yangilanib turishi mumkin** — yangi qoida yoki hujjat qo'shilsa,
tizim uni darhol ishlata boshlaydi.

---

## 7. Diagnostic Engine (diagnostika mexanizmi)

Bu loyihaning **asosiy farqlovchi qismlaridan biri.** Operatorning "so'rab-surishtirib
aniqlash" mantig'ini avtomatlashtiradi.

Misol: *"IMEI registratsiya bo'lmayapti."*
```
AI: "Qurilma O'zbekistonда sotib olinganmi yoki chetdan olib kelinganmi?"
   ↓ (javobga qarab)
AI: keyingi aniqlashtiruvchi savol
   ↓
AI: yana aniqlashtirish
   ↓
Muammoning ehtimoliy sababi
   ↓
Resolution Card (yechim kartаsi)
```

Tamoyil: **Savol → Javob → Keyingi savol → Diagnoz → Yechim.**
Bu — qaror daraxti (decision tree): har javob keyingi savolni belgilaydi va
noto'g'ri yechim chiqib ketishining oldini oladi.

---

## 8. Resolution Card (yechim kartasi)

Har bir aniqlanган muammo uchun **oldindan tasdiqlangan yechim** bo'ladi.
Resolution Card tarkibi:
- muammo nomi;
- ehtimoliy sabab;
- nima qilish kerak;
- bosqichlar;
- kerakli hujjatlar;
- qayerga murojaat qilish;
- rasmiy URL;
- telefon / kontakt;
- qachon operatorga yuborish kerak.

Buning natijasida AI **bir xil muammoga har safar butunлей boshqacha yechim
chiqarib yubormaydi** — javob standartlashtiriladi va ishonchli bo'ladi.

---

## 9. Ma'lumotlar xavfsizligi (Privacy-by-Design)

**Privacy-by-Design** — maxfiylikни boshdanoq loyihага singdirish.

AI Chat foydalanuvchidan **imkon qadar** JShShIR, pasport, telefon, karta, OTP,
parol kabi shaxsiy ma'lumotni **so'ramaydi.**

Agar foydalanuvchi o'zi yuborsa — **PII Guard** ularni AI modelga yuborilishidан
**oldin** maskalaydi:
```
+998901234567  →  [PHONE_NUMBER]
```

Rasmiy murojaat kerak bo'lganда:
```
AI Chat  →  Appeal Draft  →  Secure Form  →  Shaxsiy ma'lumot  →  Rasmiy tizim
```
Ya'ni **AI faqat murojaat matnini tayyorlaydi.** Shaxsiy ma'lumot esa **alohida
Secure Form** orqali, chat oqimidан tashqarida kiritiladi.

---

## 10. Muhim cheklov (MVP)

MVP bosqichида AI **IMEI va MNP operatsion bazаларига to'g'ridan-to'g'ri kirish
huquqiga ega emas.**

Shuning uchun AI **hech qachon** shunday yolg'on real-time javob bermaydi:
> ❌ "IMEI'ingizni tekshirdim, ro'yxatdan o'tmagan."

Buning o'rniga **diagnostik javob** beradi:
> ✅ "Siz bergan ma'lumotларга ko'ra, ehtimoliy sabab..."

Keyinchalik **xavfsiz API integratsiyasi** yaratilса, real-time status
funksiyalari **alohida bosqich** sifatida qo'shilishi mumkin.

---

## 11. API va On-Premise konsepsiyasi

MVPда AI model **API orqali** ishlatiladi (bulutдаги modelni chaqirish). Asosiy
model sifatida **iqtisodiy va katta hajmдаgi dialoglar uchun mos** model tanlanadi.

Arxitektura **model-agnostic** ("modelга bog'liq bo'lmagan") bo'lishi kerak — ya'ni
kelajakда boshqa API modeli, kuchliroq model, local/open-weight model yoki
**On-Premise** (o'z serveringizда) model bilan **almashtirish imkoniyati saqlansin.**

MVPда qimmat GPU xarid qilishдан oldin **real trafik va AI xarajatlari
o'lchansin.** Keyinchalik qaror:
```
API Cost + Traffic + Security Requirement + 3-Year TCO
```
asosида API yoki On-Premise tanlanadi. (*TCO — Total Cost of Ownership, 3 yillik
umumiy egalik xarajati.*)

---

## 12. Loyihaning biznes maqsadi

**Maqsad operatorларни to'liq almashtirish emas.** Maqsad — model o'zgartirish:
```
standart murojaatlar  →  AI Self-Service
murakkab murojaatlar  →  Human Operator (inson)
```

Natijada:
- operator yuklamasi kamayadi;
- mijoz 24/7 xizmat oladi;
- kutish vaqti kamayadi;
- standart murojaatlar tezroq hal qilinadi;
- operator murakkab holatларга ko'proq vaqt ajratadi;
- xizmat sifati standartlashtiriladi;
- murojaatlar bo'yicha analitika paydo bo'ladi.

---

## 13. Iqtisodiy samara

**Bugungi baseline:** 200 mln so'm/oy · 2,4 mlrd so'm/yil · 50 000 minut/oy.

AI operator yuklamasини kamaytirishi — uch ssenariyда:

| Ssenariy | Yuklamа kamayishi | AI'ga o'tadigan minut/oy | Bo'shaydigan vaqt | Capacity Value/yil |
|---|---|---|---|---|
| Konservativ | 20% | 10 000 | ≈167 soat/oy | **480 mln so'm** |
| **Base Case** | **35%** | **17 500** | **≈292 soat/oy** | **840 mln so'm** |
| Optimistik | 50% | 25 000 | ≈417 soat/oy | **1,2 mlrd so'm** |

**Base Case (35%)** batafsil: 17 500 minut/oy ≈ 292 operator-soat/oy ≈ 3 500
operator-soat/yil ≈ **840 mln so'm/yil Capacity Value.**

> ⚠️ **Muhim:** **Capacity Saving ≠ Cash Saving.**
> "Capacity Value" — bo'shagan vaqtning **shartli qiymati** (bu vaqtни boshqa
> ishга yo'naltirish mumkin). Bu **avtomatik ravishda pul tejash degani emas.**
> Haqiqiy **Cash Saving** faqat operator uchun **real to'lov kamaygandagina**
> (masalan tashqi outsource haqi, qo'shimcha ish haqi yoki yangi operator olmaslik)
> hisoblanadi. Real tejash **pilotда o'lchanadi** — bu hozircha gipoteza.

---

## 14. MVP nima bo'ladi?

Faqat **zarur** funksiyalar (keraksiz narsалар bilan MVPni kattalashtirmaslik):
- Web AI Assistant
- Telegram Bot
- IMEI + MNP
- Knowledge Base
- RAG
- Diagnostic Decision Trees
- Resolution Cards
- PII Guard
- Operator Escalation
- Appeal Draft (rasmiy murojaat loyihasi)
- Admin Panel
- Basic Analytics

---

## 15. Loyiha muddati

**Realistik MVP: 10–12 hafta (taxminan 3 oy).**

| Bosqich | Ish |
|---|---|
| **1-oy** | Knowledge Base + biznes jarayonlari + AI/RAG |
| **2-oy** | Backend + Web + Telegram + diagnostika |
| **3-oy** | Security + Testing + Pilot |

> 3 oyда **mukammal Production tizim emas**, balki **real foydalanuvchiларда
> sinash mumkin bo'lган, ishlaydigan MVP** tayyorlanadi.

---

## 16. Loyiha natijasini qanday o'lchaymiz?

**Eng muhim KPI — Self-Service Resolution Rate:** AI bilan gaplashgan
foydalanuvchиларning necha foizi **operatorga bormasдан** muammosини hal qildi?

Qo'shimcha KPI'lar:
- Call Deflection Rate (operatorга yetib bormagan standart murojaatlar)
- Escalation Rate (operatorга o'tkazilган ulush)
- Average Resolution Time (o'rtacha hal qilish vaqti)
- Cost per Conversation (bitta suhbat xarajati)
- Cost per Successfully Resolved Case (hal qilingan murojaat xarajati)
- AI Error / Hallucination Rate (AI xato/o'ylab topish darajasi)
- PII Leakage Rate (shaxsiy ma'lumot sizib chiqishi)
- User Satisfaction (foydalanuvchi mamnunligi)

Pilotdан keyin loyiha muvaffaqiyati aynan shu KPI'lar asosида baholanadi.

---

## 17. Kelajakдаgi rivojlanish

```
1. INTERNAL MVP
   IMEI + MNP
      ↓
2. INTERNAL ENTERPRISE PLATFORM
   Boshqa xizmat va jarayonларни ham AI Assistantга qo'shish
      ↓
3. B2B AI SERVICE
   Boshqa tashkilotlar uchun ularning o'z jarayonlari asosида
   Enterprise AI Assistant yaratish
```

**Muhim:** Bizning IMEI/MNP bilim bazasi, ichki ma'lumotlar va biznes qoidалаrimiz
**boshqa tashkilotларга berilmaydi.** Har bir tashkilot uchun **alohida** quriladi:
```
Business Process Analysis  →  Uning Knowledge Base'i  →  Uning Decision Trees
   →  Uning integratsiyalari  →  Uning Enterprise AI Assistant'i
```

**Kelajakдаgi daromad modeli:** Implementation Fee · Integration Fee · Custom
Development · Annual Support · Maintenance.

> B2B bosqich **faqat ichki loyiha real KPI va iqtisodiy samарани
> ko'rsatgandан keyin** boshlanadi.

---

## Yakuniy natija — uch darajада

### 1. Bir jumlada (rahbarга 15 soniyada)
Mijozning IMEI/MNP muammosини operator kabi savol-javob bilan diagnostika qilib,
kompaniyaning tasdiqlangan bilimlari asosида yechim beradigan va kerak bo'lганда
inson operatorига to'g'ri yo'naltiradigan, Web va Telegramда 24/7 ishlaydigan
Enterprise AI Assistant.

### 2. Bir paragrafда
Loyiha operatorларning vaqtини eng ko'p oladigan standart IMEI va MNP
murojaatларини AI self-service kanalига o'tkazadi. Tizim oddiy chatbot emas: u
mijoz muammosини tushunadi, diagnostik savollar orqali sababни toraytiradi,
kompaniyaning tasdiqlanган bilim bazасidан (RAG orqali) aniq faktни topadi va
bosqichma-bosqich yechim beradi; hal qila olmаsа — operatorga yoki rasmiy
murojaatга yo'naltiradi. Shaxsiy ma'lumot PII Guard bilan himoyalanadi, faktlar
esa hech qачон o'ylab topilmaydi. Biznes qiymati: operator yuklamаsi kamayadi,
mijoz 24/7 tezroq va standart xizmat oладi, operatorlar murakkab holatларга
vaqt ajratadi — real tejash pilotда o'lchanadi.

### 3. To'liq konsepsiya
Yuqorида: **Muammo** (§2) → **Yechim/farq** (§1, §3) → **Arxitektura** (§4–8) →
**Xavfsizlik** (§9–10) → **MVP** (§11, §14, §15) → **KPI** (§16) → **Iqtisodiy
samара** (§13) → **Kelajакdаgi B2B model** (§17).

---

> **Asosiy urg'u:** "Biz chatbot yaratmayapmiz. Biz mijoz muammosини tushunadigan,
> diagnostika qiladigan, kompaniyaning tasdiqlangan bilimlari asosида yechim
> beradigan va zarur holatда inson operatorига to'g'ri eskalatsiya qiladigan
> Enterprise AI Assistant yaratmoqdamiz."
