# -*- coding: utf-8 -*-
"""
Tasdiqlangan FAQ bilim bazasi (IMEI + MNP).
Manba: "MNP va IMEI FAQ.docx" — O'zTTBRM.

Har bir yozuv:
  q      — asosiy savol (uz_latn)
  alt    — muqobil formulalar (uz_latn / uz_cyrl / ru) — hybrid qidiruv uchun
  a      — javob matni
  refs   — normativ havolalar
  case   — taxonomy.CASE_TYPES kaliti
  domain — imei | mnp
"""

FAQ = [
 # ----------------------------------------------------------------- IMEI
 dict(domain="imei", case="royxatdan_otkazish",
   q="Mobil qurilmaning IMEI-kodini qanday bilish mumkin?",
   alt=["IMEI qanday tekshiriladi", "IMEI кодини қандай билиш мумкин",
        "как узнать IMEI телефона"],
   a="Qurilma klaviaturasida *#06# kombinatsiyasini tering. IMEI-kod, shuningdek, "
     "qurilma qutisida, kafolat kartasida, ayrim modellarda batareya ostida yozilgan bo‘ladi.",
   refs=[]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="IMEI-kod holatini qayerdan tekshirish mumkin?",
   alt=["IMEI holati", "IMEI статуси", "проверить статус IMEI"],
   a="Uch usul bor: 1) www.uzimei.uz saytida; 2) 1170 qisqa raqamiga SMS yuborib; "
     "3) *1170# USSD so‘rovi orqali.",
   refs=[]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="Jismoniy shaxs-rezident IMEI-kodni qayerda ro‘yxatdan o‘tkazadi?",
   alt=["rezident IMEI ro'yxatdan o'tkazish", "резидент IMEI рўйхатдан ўтказиш",
        "где зарегистрировать IMEI резиденту"],
   a="www.uzimei.uz saytida; www.my.gov.uz (YIDXP) portali yoki mobil ilovasida; "
     "Birda mobil ilovasida; UZIMEI tizimi operatori ofisida (Toshkent sh., Olmazor tum., "
     "Sebzor mavzesi, 18-A, mo‘ljal: 240 ATS binosi); mobil aloqa operatorlari "
     "(MobiUz, UCELL, UZTELECOM) ofislarida. Olib kirishda bojxona to‘lovi undirilmaydigan "
     "me’yordan qat’i nazar deklaratsiya to‘ldiriladi. IMEI-kod SIM-karta almashtirilishidan "
     "qat’i nazar bir marta ro‘yxatga olinadi.",
   refs=["VMQ 463-son", "VMQ 778-son"]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="Jismoniy shaxs-norezident IMEI-kodni qanday ro‘yxatdan o‘tkazadi?",
   alt=["norezident IMEI", "норезидент IMEI", "нерезидент регистрация IMEI"],
   a="www.uzimei.uz saytida yoki UZIMEI tizim operatori ofisida, shuningdek mobil aloqa "
     "operatorlarida (MobiUz, UCELL, UZMOBILE). Mahalliy SIM-karta sotib olishda uni "
     "norezident maqomi bilan rasmiylashtirish kerak. Ro‘yxatdan o‘tkazish muddati — "
     "SIM-slot faollashtirilgandan keyin 60 kalendar kun.",
   refs=["VMQ 463-son", "VMQ 778-son"]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="IMEI-kodni ro‘yxatdan o‘tkazish muddati qancha?",
   alt=["necha kun ichida ro'yxatdan o'tkazish kerak", "муддат IMEI",
        "срок регистрации IMEI"],
   a="SIM-slot faollashtirilgan paytdan boshlab: rezidentlar uchun 30 kalendar kun, "
     "norezidentlar uchun 60 kalendar kun. Muddat o‘tkazib yuborilsa, IMEI ro‘yxatdan "
     "o‘tkazilmaguncha abonent mahalliy GSM tarmoq xizmatlaridan foydalana olmaydi.",
   refs=["VMQ 778-son"]),

 dict(domain="imei", case="tolov_tarif",
   q="IMEI-kodni ro‘yxatdan o‘tkazish qancha turadi?",
   alt=["IMEI narxi", "tarif IMEI", "IMEI нархи", "стоимость регистрации IMEI", "сколько стоит регистрация IMEI", "цена регистрации IMEI"],
   a="2025-yil 1-avgustdan amal qiluvchi tariflar (bazaviy hisoblash miqdori 412 000 so‘m): "
     "rezident/norezident jismoniy shaxs 30 kalendar kun ichida — 82 400 so‘m (BHMning 20%); "
     "30 kundan keyin — 103 000 so‘m (25%); import qiluvchi — 82 400 so‘m (20%); "
     "mahalliy ishlab chiqaruvchi — 41 200 so‘m (10%); norezident chet el SIM-kartasidan "
     "rouming rejimida foydalansa — 0 so‘m.",
   refs=[]),

 dict(domain="imei", case="tolov_tarif",
   q="Ro‘yxatga olish to‘lovini qanday amalga oshirish mumkin?",
   alt=["to'lov usullari", "тўлов усуллари", "как оплатить регистрацию IMEI"],
   a="Payme, Click, Upay to‘lov tizimlari orqali (shu jumladan Telegram-bot), "
     "shuningdek O‘zbekiston Respublikasi hududidagi banklar orqali.",
   refs=[]),

 dict(domain="imei", case="blokdan_chiqarish",
   q="Mobil qurilmaning IMEI-kodini qanday blokdan chiqarish mumkin?",
   alt=["telefon bloklandi", "қурилма блокдан чиқариш", "разблокировать IMEI"],
   a="Qurilmaning IMEI-kodini UZIMEI tizimida ro‘yxatdan o‘tkazish kerak. "
     "Ro‘yxatdan o‘tgach, qurilmani o‘chirib-yoqish talab etiladi.",
   refs=[]),

 dict(domain="imei", case="klon_imei",
   q="Klonlangan yoki aniqlanmagan IMEI-kodli qurilma ro‘yxatga olinadimi?",
   alt=["klon IMEI", "клонланган IMEI", "клонированный IMEI"],
   a="Yo‘q. 778-son VMQ bilan tasdiqlangan nizomning 3-bob 7-bandiga muvofiq klonlangan va "
     "aniqlanmagan IMEI-kodli mobil qurilmalar Tizimda ro‘yxatga olinmaydi. 6-bob 39-bandiga "
     "asosan klonlangan IMEI aniqlanganda tizim avtomatik tahlil qilib, qurilmani "
     "«qora ro‘yxat»ga kiritadi. Qurilma respublika hududidan sotib olingan bo‘lsa, "
     "61-bandga muvofiq uni ro‘yxatdan o‘tkazish uchun chakana savdo bilan shug‘ullanuvchi "
     "tadbirkorlik subyekti javobgar bo‘ladi.",
   refs=["VMQ 778-son 7-band", "VMQ 778-son 39-band", "VMQ 778-son 61-band"]),

 dict(domain="imei", case="eski_qurilma",
   q="Abonent raqamini IMEI-kodga bog‘lash nimani anglatadi?",
   alt=["raqam IMEI ga bog'langan", "рақам IMEI га боғланган",
        "номер привязан к IMEI"],
   a="Avtomatik ro‘yxatdan o‘tish davrida (2019.04.01 — 2019.10.31) IMEI-kodi aniqlanmagan "
     "yoki klonlangan qurilmalar abonent raqamiga bog‘lash sharti bilan ro‘yxatdan o‘tgan. "
     "Bunday qurilmalar tarmoq hodisalarini (qo‘ng‘iroq, SMS) faqat bog‘langan raqam orqali "
     "amalga oshira oladi. Bog‘langan raqamni o‘zgartirish uchun Tizim operatori yoki "
     "Tizim ro‘yxatga oluvchisiga murojaat qilish kerak.",
   refs=[]),

 dict(domain="imei", case="bojxona",
   q="Bojsiz olib kirish me’yoridan ortiq qurilma olib kirilsa nima bo‘ladi?",
   alt=["bojxona kirim orderi", "божхона", "таможенный ордер IMEI"],
   a="Me’yor (yarim yilda bitta qurilma, planshetlardan tashqari) oshirilgan bo‘lsa, "
     "IMEI-kod tizim operatoriga bojxona kirim orderi taqdim etilgandan keyin ro‘yxatga "
     "olinadi. Yarim yillar: 1-yanvar — 30-iyun va 1-iyul — 31-dekabr. Me’yor davlat "
     "chegarasini avtomobil (piyoda), temir yo‘l va daryo o‘tkazish punktlari orqali "
     "kesib o‘tishga nisbatan qo‘llaniladi.",
   refs=["VMQ 463-son", "O‘zR DBQ 526-son nizom"]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="Xalqaro pochta yoki kuryerlik jo‘natmasi orqali kelgan qurilma qanday ro‘yxatga olinadi?",
   alt=["pochta orqali telefon", "почта орқали", "посылка телефон IMEI"],
   a="Tizim operatori yoki Tizim ro‘yxatga oluvchisiga shaxsan murojaat qilib, pochta "
     "identifikatorining shtrix kodi, kalendar shtempeli bo‘lgan konvert va jo‘natma "
     "oluvchisining pasportini ko‘rsatish orqali; shuningdek tizim operatorining sayti orqali.",
   refs=[]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="O‘zbekiston hududida sotib olingan qurilmaning IMEI-kodini kim ro‘yxatdan o‘tkazadi?",
   alt=["kim ro'yxatdan o'tkazadi", "ким рўйхатдан ўтказади",
        "кто регистрирует IMEI"],
   a="Sotish uchun respublika hududiga olib kirgan shaxs (yuridik shaxs yoki import qiluvchi) "
     "778-son VMQga muvofiq ro‘yxatdan o‘tkazadi. Iste’molchi qurilmani sotib olishdan oldin "
     "IMEI holatini www.uzimei.uz saytida yoki *1170# orqali tekshirishi kerak. "
     "Ro‘yxatga olishda foydalanilgan abonent raqami arizachining nomiga rasmiylashtirilgan "
     "bo‘lishi shart.",
   refs=["VMQ 778-son"]),

 dict(domain="imei", case="yoqotilgan_ogirlangan",
   q="Mobil qurilma yo‘qolsa yoki o‘g‘irlansa nima qilish kerak?",
   alt=["telefon o'g'irlandi", "телефон йўқолди", "украли телефон"],
   a="Ichki ishlar boshqarmasiga ariza bilan murojaat qilish lozim. Arizada qurilmaning "
     "ishlab chiqaruvchisi, modeli va IMEI-kodi/kodlari ko‘rsatilishi kerak.",
   refs=[]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="Qurilmada ikki va undan ortiq IMEI-kod bo‘lishi nimani anglatadi?",
   alt=["ikkita IMEI", "иккита IMEI", "два IMEI"],
   a="Qurilmaga bir vaqtning o‘zida ikki va undan ortiq SIM-karta yordamida ikki va undan "
     "ortiq uyali aloqa operatori xizmat ko‘rsatishi mumkin.",
   refs=[]),

 dict(domain="imei", case="aniqlanmagan_imei",
   q="TAC raqami GSMA bazasidagi qurilma turiga mos kelmasa nima qilinadi?",
   alt=["TAC raqami mos emas", "GSMA база", "TAC не соответствует"],
   a="1-sonli Nizomga ko‘ra quyidagi qurilmalar foydalanuvchi ishtirokisiz, ilk tarmoq "
     "hodisasidan so‘ng avtomatik ro‘yxatga olinadi: DONGLE, WLAN ROUTER, IoT DEVICE, "
     "VEHICLE, E-BOOK, MODULE (GSM/GPRS va GPS modulli qurilmalar, GPS-treker, POS-terminal), "
     "CONNECTED COMPUTER, MODEM, WEARABLES. Agar TAC raqami GSMA bazasidagi qurilma turiga "
     "mos kelmasa, arizachi IMEI-kodga o‘zgartirish kiritish uchun ishlab chiqaruvchiga "
     "murojaat qilishi kerak; o‘zgartirishdan keyin ro‘yxatga olish avtomatik amalga oshadi.",
   refs=["1-sonli Nizom"]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="Fuqaroligi bo‘lmagan shaxs IMEI-kodni qanday ro‘yxatdan o‘tkazadi?",
   alt=["fuqaroligi yo'q shaxs", "фуқаролиги бўлмаган", "лицо без гражданства IMEI"],
   a="Vazirlar Mahkamasi belgilagan tartibda berilgan biometrik harakatlanish hujjati orqali, "
     "UZIMEI tizimi operatori ofisida (Toshkent sh., Olmazor tum., Sebzor mavzesi, 18-A). "
     "Bojsiz olib kirish limiti oshirilgan bo‘lsa, ro‘yxatga olish bojxona kirim orderi "
     "taqdim etilgandan keyin amalga oshiriladi.",
   refs=["PQ 3512-son", "VMQ 463-son", "O‘zR DBQ 526-son nizom"]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="JSHSHIR nima?",
   alt=["JSHSHIR", "ЖШШИР", "ПИНФЛ что это"],
   a="JSHSHIR — jismoniy shaxsning shaxsiy identifikatsiya raqami, 14 ta raqamdan iborat. "
     "U jismoniy shaxsning pasportida ko‘rsatiladi.",
   refs=[]),

 # ----------------------------------------------------------------- MNP
 dict(domain="mnp", case="mnp_tartib",
   q="MNP.UZ nima?",
   alt=["MNP xizmati", "MNP хизмати", "что такое MNP"],
   a="MNP.UZ — O‘zbekiston hududida GSM standartidagi mobil aloqa abonentlariga o‘z telefon "
     "raqamini saqlab qolgan holda mobil aloqa operatorini almashtirish imkonini beruvchi "
     "xizmat. Abonent raqami va kontaktlarini yo‘qotmasdan tarif, sifat yoki xizmat shartlari "
     "ma’qul bo‘lgan boshqa operatorga o‘tishi mumkin.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="Qaysi operatorlar GSM standarti bo‘yicha ishlaydi?",
   alt=["operatorlar ro'yxati", "операторлар", "список операторов GSM"],
   a="Beeline, Mobi.uz, Ucell, UZTELECOM, Humans — jami 5 ta mobil aloqa operatori.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="Operator almashtirilganda raqam shakli saqlanadimi?",
   alt=["raqam o'zgaradimi", "рақам ўзгарадими", "номер изменится"],
   a="Yo‘q, ko‘chirilgan raqamlar o‘z shakli va to‘kisligini saqlab qoladi.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="CDMA operatoridan raqamni ko‘chirish mumkinmi?",
   alt=["CDMA ko'chirish", "CDMA кўчириш", "перенос номера CDMA"],
   a="Hozirgi vaqtda bunday texnik imkoniyat yo‘q — CDMA operatori raqamlarini ko‘chirib "
     "bo‘lmaydi. Xizmat faqat GSM standartida faoliyat yurituvchi operatorlar abonentlariga "
     "taqdim etiladi.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="Operatorni qayta almashtirish uchun qancha kutish kerak?",
   alt=["30 kun MNP", "30 кун", "через сколько можно снова перейти"],
   a="Abonent operatorni cheklanmagan miqdorda almashtirishi mumkin, lekin har bir navbatdagi "
     "ko‘chirish avvalgi ko‘chirish sanasidan kamida 30 kun o‘tgach amalga oshiriladi.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="Operator almashtirilganda balansdagi pul ko‘chadimi?",
   alt=["balans ko'chadimi", "баланс", "переносится ли баланс"],
   a="Yo‘q. Mablag‘larni bir operator hisobidan boshqasiga to‘g‘ridan-to‘g‘ri ko‘chirish "
     "texnik jihatdan imkonsiz. Mablag‘ni qaytarish uchun oldingi operator ofisiga ariza "
     "bilan murojaat qilish mumkin.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="MNP uchun qanday hujjatlar kerak?",
   alt=["MNP hujjatlar", "MNP ҳужжатлар", "документы для MNP"],
   a="Jismoniy shaxs — raqamni ro‘yxatga olishda qo‘llanilgan shaxsni tasdiqlovchi hujjatni; "
     "yuridik shaxs — tashkilotning STIRini taqdim etadi. Ariza abonent o‘tmoqchi bo‘lgan "
     "yangi operator ofisida to‘ldiriladi.",
   refs=[]),

 dict(domain="mnp", case="mnp_ariza_rad",
   q="Raqamni ko‘chirish arizasi qanday hollarda rad etiladi?",
   alt=["ariza rad etildi", "ариза рад этилди", "отказ в переносе номера"],
   a="To‘rt asosiy sabab: 1) arizadagi ma’lumotlar oldingi operator bazasiga mos kelmasligi "
     "(raqam, FISH, pasport ma’lumotlari); 2) oldingi operator oldida qarzdorlik; "
     "3) oxirgi ko‘chirishdan 30 kun o‘tmaganligi; 4) raqamning oldingi operator tomonidan "
     "bloklanganligi (SIM yo‘qolgani, sud qarori yoki to‘lov qilinmagani sababli).",
   refs=[]),

 dict(domain="mnp", case="mnp_ariza_rad",
   q="Ma’lumotlar mos kelmagani uchun rad etilsa nima qilish kerak?",
   alt=["FISH mos emas", "маълумотлар мос эмас", "данные не совпадают"],
   a="Oldingi operatorning sotuv va xizmat ko‘rsatish bo‘limiga murojaat qilib, ma’lumotlarni "
     "to‘g‘rilash kerak. Raqam egasining FISH va pasport ma’lumotlari mos kelishi majburiy "
     "talab. So‘ng ariza qayta topshiriladi.",
   refs=[]),

 dict(domain="mnp", case="mnp_ariza_rad",
   q="Qarzdorlik sababli rad etilsa nima qilish kerak?",
   alt=["qarzdorlik MNP", "қарздорлик", "задолженность перенос номера"],
   a="Oldingi operator oldidagi qarzdorlikni qulay usulda so‘ndirish, so‘ng yangi operatorning "
     "sotuv va xizmat ko‘rsatish ofislaridan birida arizani takroran topshirish lozim. "
     "Rouming xizmati bo‘yicha qarzdorlik aniqlansa ham, blokdan chiqarish uchun oldingi "
     "operator ofisiga murojaat qilinadi.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="Boshqa shaxs nomidagi raqamni ko‘chirish uchun ariza bera olamanmi?",
   alt=["boshqa odam raqami", "бошқа шахс рақами", "перенести чужой номер"],
   a="Faqat raqam egasi yoki ishonchnoma asosida uning vakili ariza berishi mumkin. "
     "Raqamni boshqa shaxs nomiga rasmiylashtirish uchun ikkala abonent tegishli hujjatlar "
     "bilan operator ofisiga birgalikda murojaat qiladi; shaxsan kelish imkoni bo‘lmasa, "
     "operatsiya ishonchnoma asosida bajariladi.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="Raqam ko‘chirilgani haqida qanday xabar beriladi?",
   alt=["SMS xabar MNP", "хабар", "уведомление о переносе"],
   a="Yangi operator (resipient-operator) ko‘chirish jarayoni muvaffaqiyatli yakunlangani "
     "haqida yangi SIM-kartaga SMS yuboradi. Barcha shartlar bajarilgan bo‘lsa, jarayon "
     "ko‘p vaqt talab qilmaydi.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="MNP xizmati uchun to‘lov qanday amalga oshiriladi?",
   alt=["MNP narxi", "MNP нархи", "стоимость переноса номера"],
   a="To‘lov bir martalik bo‘lib, yangi xizmat kelishuvi tuzilayotganda abonent o‘tayotgan "
     "operatorga (resipient-operatorga) to‘lanadi. To‘lov hajmi har bir operator tomonidan "
     "mustaqil belgilanadi, shuning uchun operatorlarda farq qilishi mumkin.",
   refs=[]),

 dict(domain="mnp", case="mnp_tartib",
   q="Operator sifati yoqmasa, eski operatorga qaytish mumkinmi?",
   alt=["orqaga qaytish", "орқага қайтиш", "вернуться к прежнему оператору"],
   a="Ha, lekin 30 taqvim kuni o‘tganidan so‘ng.",
   refs=[]),
]
