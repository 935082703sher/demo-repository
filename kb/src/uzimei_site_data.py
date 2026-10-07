# -*- coding: utf-8 -*-
"""uzimei.uz rasmiy saytidagi xizmatlar va ro'yxatdan o'tish usullari.

Manba: uzimei.uz bosh sahifasi ("IMEI-kodini ro'yxatdan o'tkazish holatini
tekshirish", "Ariza raqami bo'yicha ro'yxatdan o'tkazish uchun onlayn to'lov",
"Rezident va norezidentlar uchun IMEI-kodlarini onlayn ro'yxatdan o'tkazish",
"Ro'yxatdan o'tish usullari": Birda / MyGov / Operatorlar, "Ro'yxatdan o'tkazish
nuqtalari") va sayt FAQ matni, 07.10.2026 holatiga. Onlayn ro'yxat qadamlari
UZIMEI bilim bazasining D03 bo'limidan (uzimei.uz, 25.09.2026 tekshirilgan) olingan.
Faqat saytdagi matn qayta yozilgan — yangi fakt, muddat yoki summa qo'shilmagan.

Mavjud FAQ (faq_data.py) bu savollarning ko'pini qamraydi; bu yozuvlar mijozlar
ko'p ishlatadigan "online/onlayn", "Birda", "MyGov", "ariza raqami" so'zlari bilan
yozilgan savollar ham to'g'ri javobni topishi uchun qo'shildi.
"""

SITE_SOURCE = "uzimei.uz rasmiy sayti (bosh sahifa va FAQ)"

SITE = [
 dict(domain="imei", case="royxatdan_otkazish",
   q="IMEI-kodni onlayn ro‘yxatdan o‘tkazish mumkinmi va qayerda?",
   alt=["imei online royxatdan otkazish", "imeini online royxatdan otkazishga yordam",
        "imeini onlayn ro'yxatdan o'tkazish tartibi",
        "internet orqali IMEI ro'yxatdan o'tkazish", "uydan turib ro'yxatdan o'tkazish",
        "uzimei.uz saytida ro'yxatdan o'tkazish", "IMEI онлайн рўйхатдан ўтказиш",
        "зарегистрировать IMEI онлайн", "register IMEI online"],
   a="Ha, onlayn ro‘yxatdan o‘tkazish mumkin — www.uzimei.uz saytida, YIDXPning "
     "www.my.gov.uz portali yoki MyGov mobil ilovasida (jismoniy shaxslar uchun) va Birda "
     "mobil ilovasida (rezident va norezident jismoniy shaxslar uchun). uzimei.uz saytida "
     "tartib: 1) telefon klaviaturasida *#06# terib IMEI-kodni bilib oling (bir nechta "
     "bo‘lsa, har biri alohida); 2) bosh sahifada «O‘zbekiston Respublikasi rezident va "
     "norezidentlari uchun mobil qurilmaning IMEI-kodlarini onlayn ro‘yxatdan o‘tkazish» "
     "blokini toping; 3) undagi «IMEI-kodni kiriting» maydoniga kodni o‘zingiz kiriting va "
     "«Tekshirish»ni bosing; 4) shaxsni tasdiqlash, telefon raqami, SMS, biometrik tekshiruv "
     "yoki to‘lov so‘ralsa, jarayonni saytda o‘zingiz davom ettiring — keyingi ekran IMEI "
     "holatiga bog‘liq; 5) ariza ochilishi ro‘yxat yakunlanganini anglatmaydi: yakuniy "
     "holatni bosh sahifadagi «IMEI-kodini ro‘yxatdan o‘tkazish holatini tekshirish» bloki "
     "orqali tekshiring. Ro‘yxatga olishda foydalanilgan abonent raqami mahalliy mobil "
     "operatorda arizachining nomiga rasmiylashtirilgan bo‘lishi kerak. O‘zbekistondagi "
     "do‘kondan olingan telefon bo‘lsa, avval sotuvchiga murojaat qiling. Xalqaro pochta yoki "
     "kuryerlik jo‘natmasi orqali kelgan qurilma ham sayt orqali ro‘yxatdan o‘tkazilishi "
     "mumkin (pochta identifikatorining shtrix kodi, kalendar shtempeli bo‘lgan konvert va "
     "jo‘natma oluvchining pasporti bilan).",
   refs=["VMQ 778-son"]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="IMEI-kodni ro‘yxatdan o‘tkazishning qanday usullari bor (Birda, MyGov, operatorlar)?",
   alt=["ro'yxatdan o'tish usullari", "Birda orqali IMEI ro'yxatdan o'tkazish",
        "MyGov orqali IMEI ro'yxatdan o'tkazish", "operator ofisida ro'yxatdan o'tkazish",
        "qayerda ro'yxatdan o'tkazsam bo'ladi", "ro'yxatdan o'tkazish nuqtalari",
        "рўйхатдан ўтиш усуллари", "способы регистрации IMEI", "Birda MyGov"],
   a="IMEI-kodni quyidagi usullarda ro‘yxatdan o‘tkazish mumkin: 1) Tizim operatorining "
     "www.uzimei.uz veb-saytida; 2) YIDXPning www.my.gov.uz portali va MyGov mobil "
     "ilovasida — jismoniy shaxslar uchun; 3) Birda mobil ilovasida — rezident va "
     "norezident jismoniy shaxslar uchun; 4) Tizim operatorida (Toshkent sh., Olmazor "
     "tum., Sebzor mavzesi, 18-A, mo‘ljal: 240 ATS binosi); 5) mobil aloqa operatorlari "
     "ofislarida — rezidentlar va norezidentlar o‘zi kelgan holda. Ro‘yxatdan o‘tkazish "
     "nuqtalari uzimei.uz saytidagi xaritada shahar bo‘yicha ko‘rsatilgan. IMEI-kod "
     "SIM-karta almashtirilishidan qat’i nazar bir marta ro‘yxatga olinadi.",
   refs=["VMQ 463-son", "VMQ 778-son"]),

 dict(domain="imei", case="tolov_tarif",
   q="Ariza raqami bo‘yicha ro‘yxatdan o‘tkazish to‘lovini onlayn qanday to‘layman?",
   alt=["ariza raqami bo'yicha to'lov", "SMS kelgan ariza raqami", "onlayn to'lov IMEI",
        "ariza raqamini kiritib to'lash", "ариза рақами бўйича тўлов",
        "оплата по номеру заявки IMEI", "pay IMEI registration online"],
   a="www.uzimei.uz saytining bosh sahifasidagi «Ariza raqami bo‘yicha ro‘yxatdan "
     "o‘tkazish uchun onlayn to‘lov» bo‘limida SMS orqali yuborilgan ariza raqamini "
     "kiriting va «To‘lash» orqali to‘lovni amalga oshiring. To‘lovni Payme, Click, Upay "
     "to‘lov tizimlari (shu jumladan Telegram-bot) orqali, shuningdek O‘zbekiston "
     "Respublikasi hududidagi banklarda ham amalga oshirish mumkin.",
   refs=[]),

 dict(domain="imei", case="royxatdan_otkazish",
   q="IMEI-kod ro‘yxatdan o‘tganini qanday tekshiraman?",
   alt=["ro'yxatdan o'tganmi tekshirish", "IMEI holatini tekshirish saytda",
        "ro'yxatdan o'tkazish holatini tekshirish", "*1170#", "проверить регистрацию IMEI"],
   a="www.uzimei.uz saytining bosh sahifasidagi «IMEI-kodini ro‘yxatdan o‘tkazish "
     "holatini tekshirish» bo‘limida IMEI-kodni kiritib «Tekshirish» tugmasini bosing. "
     "Shuningdek 1170 qisqa raqamiga SMS yuborib yoki *1170# USSD so‘rovi orqali "
     "tekshirish mumkin. IMEI-kodni bilish uchun *#06# kombinatsiyasini tering. "
     "Qurilmani sotib olishdan oldin ham uning IMEI-kodi holatini tekshirish tavsiya etiladi.",
   refs=[]),
]
