# -*- coding: utf-8 -*-
"""
VMQ 778-son (17.09.2019) — «Oʻzbekiston Respublikasida mobil qurilmalarni
hisobga olish tartibi toʻgʻrisidagi nizom» ning muhim (substantiv) qoidalari.

authority = 2 (normativ hujjat qatlami). Faqat qidiruvga qimmatli qoidalar
tanlab olindi (ta'riflar, ro'yxatga olish tartibi, klon/qora ro'yxat, import
va chakana javobgarligi). Manba matnidan verbatim, kod bilan qayta quriladi.
"""

VMQ778 = [
    dict(
        title="2-band. Asosiy tushunchalar: IMEI va GSMA",
        domain="imei", case_type="royxatdan_otkazish",
        tags=["imei", "gsma", "tac", "taʼrif", "определение imei"],
        text="IMEI (International Mobile Equipment Identifier) — har bir mobil qurilma "
             "uchun oʻziga xos boʻlgan 15 raqamdan iborat xalqaro mobil qurilmalar "
             "identifikatori. Asosiy identifikator GSMA tomonidan belgilangan maxsus TAC "
             "hisoblanadi. Mobil qurilma bir yoki undan ortiq IMEI koddan iborat boʻlishi "
             "mumkin. GSMA (Global System for Mobile Communication Association) — TAC kodini "
             "taqsimlash boʻyicha global boshqaruvchi; u IMEI orqali qurilma ishlab "
             "chiqaruvchisi va modelini aniq identifikatsiyalash imkonini beradi.",
    ),
    dict(
        title="2-band. Klonlangan va aniqlanmagan IMEI-kod ta'rifi",
        domain="imei", case_type="klon_imei",
        tags=["klonlangan", "aniqlanmagan", "клонированный imei", "tekshirish"],
        text="Klonlangan IMEI-kod — GSMA tomonidan belgilangan boshqa mobil qurilma "
             "IMEI-kodining belgilari va ramzlarini toʻliq qaytaruvchi mobil qurilmaning "
             "IMEI-kodi. Aniqlanmagan IMEI-kod — GSMA tomonidan belgilangan talablarga "
             "javob bermaydigan mobil qurilmaning IMEI-kodi. IMEI-kodlarni tekshirish — "
             "aniqlanmagan va klonlangan IMEI-kodlarni, shuningdek yoʻqotilgan va "
             "oʻgʻirlangan mobil qurilmalarni aniqlash uchun ularning IMEI-kodlarini Tizim "
             "bazasi bilan taqqoslash.",
    ),
    dict(
        title="2-band. Oq, qora va kul rang ro'yxatlar",
        domain="imei", case_type="blokdan_chiqarish",
        tags=["qora roʻyxat", "kul rang", "oq roʻyxat", "чёрный список", "blok"],
        text="Qora roʻyxat — tizimda roʻyxatdan oʻtmagan, klonlangan, IMEI kodi aniqlanmagan "
             "yoki GSMAning qora roʻyxatida boʻlgan mobil qurilmalar IMEI kodlari. Qora "
             "roʻyxatga kiritilgan IMEI-kod mobil aloqa xizmatlaridan foydalanishi cheklanib, "
             "abonentga sababi haqida SMS ogohlantirish yuboriladi. Kul rang roʻyxat — oq yoki "
             "qora roʻyxatga kiritilmagan, birinchi tarmoq hodisasidan boshlab 30 kalendar "
             "kundan koʻp boʻlmagan muddatga xizmatlardan foydalanadigan qurilmalar (norezident "
             "qurilmalar uchun bir kalendar yil davomida 60 kalendar kun).",
    ),
    dict(
        title="3-band 5-6. Xariddan oldin tekshirish va ro'yxatga olish majburiyligi",
        domain="imei", case_type="royxatdan_otkazish",
        tags=["tekshirish", "majburiy", "uzimei.uz", "*1170#", "xarid"],
        text="Import qiluvchilar va jismoniy shaxslar Oʻzbekiston Respublikasi hududida "
             "qurilmani xarid qilishdan avval IMEI-kodning maqomini tekshirishlari va "
             "aniqlanmagan, klonlangan, yoʻqotilgan yoki oʻgʻirlangan qurilmalarni aniqlash "
             "uchun SMS/USSD soʻrov yuborishlari yoki www.uzimei.uz saytiga murojaat "
             "qilishlari mumkin. Oʻzbekiston Respublikasi hududiga olib kirilgan, hududida "
             "ishlab chiqarilayotgan va foydalanilayotgan mobil qurilmalarni roʻyxatdan "
             "oʻtkazish majburiydir; roumingda boʻlib, mahalliy tarmoqda ilgari tarmoq "
             "hodisasi qayd etilmagan qurilmalar bundan mustasno.",
    ),
    dict(
        title="3-band 7. Klonlangan va aniqlanmagan qurilmalar ro'yxatga olinmaydi",
        domain="imei", case_type="klon_imei",
        tags=["klonlangan", "roʻyxatga olinmaydi", "qora roʻyxat"],
        text="Klonlangan va aniqlanmagan IMEI-kodli mobil qurilmalar Tizimda roʻyxatga "
             "olinmaydi. Klonlangan IMEI aniqlanganda tizim avtomatik tahlil qilib qurilmani "
             "«qora roʻyxat»ga kiritadi.",
    ),
    dict(
        title="3-band 61. Chakana savdo subyektlarining javobgarligi",
        domain="imei", case_type="royxatdan_otkazish",
        tags=["chakana", "savdo", "javobgar", "tadbirkor"],
        text="Oʻzbekiston Respublikasi hududida mobil qurilmalar chakana savdosi bilan "
             "shugʻullanuvchi tadbirkorlik subyektlari mobil qurilmalarni respublika hududiga "
             "olib kirish sanasidan qatʼiy nazar, ularni roʻyxatdan oʻtkazish uchun javobgar "
             "boʻladilar.",
    ),
    dict(
        title="4-bob 11. Import qiluvchi va ishlab chiqaruvchi tomonidan ro'yxatga olish",
        domain="imei", case_type="royxatdan_otkazish",
        tags=["import", "im-40", "bojxona", "3 kun", "ishlab chiqaruvchi"],
        text="Import qiluvchilar tomonidan olib kirilayotgan mobil qurilmalarning Tizimda "
             "roʻyxatga olinishi «erkin muomalaga chiqarish» (IM-40) bojxona rejimiga "
             "rasmiylashtirilganidan soʻng uch kun muddatda amalga oshiriladi. Chetdan "
             "keltiriladigan qurilmalarning IMEI-kodlari toʻgʻrisidagi elektron maʼlumot "
             "import qiluvchilar tomonidan majburiy tartibda bojxona yuk deklaratsiyasining "
             "31-ustunida koʻrsatilishi lozim.",
    ),
    dict(
        title="Qaror. Tizimni bosqichma-bosqich joriy etish sanalari (2019)",
        domain="imei", case_type="royxatdan_otkazish",
        tags=["2019", "muddat", "joriy etish", "aktivlashtirish"],
        text="Tizim bosqichma-bosqich joriy etilgan: 2019-yil 1-noyabrgacha qurilmalar mobil "
             "aloqa operatorlari tarmoqlariga ulash (aktivlashtirish) orqali bepul asosda "
             "avtomatik roʻyxatga olingan; 2019-yil 1-noyabrdan jismoniy shaxslar, import "
             "qiluvchilar va ishlab chiqaruvchilar mobil qurilmalarni Nizomga muvofiq "
             "IMEI-kodlari boʻyicha roʻyxatga olishni boshlagan.",
    ),
    dict(
        title="tarmoq hodisasi ta'rifi",
        domain="imei", case_type="royxatdan_otkazish",
        tags=["tarmoq hodisasi", "sim", "ulash", "aktivlashtirish"],
        text="Tarmoq hodisasi — mobil qurilmani mobil aloqa operatorining tarmogʻiga uning "
             "abonent SIM-kartasidan foydalanish orqali ulash. Roʻyxatga olish muddatlari "
             "SIM-slot faollashtirilgan (birinchi tarmoq hodisasi) paytdan boshlab hisoblanadi.",
    ),
    dict(
        title="5-bob 101. Diplomatik vakolatxonalar uchun tartib",
        domain="imei", case_type="royxatdan_otkazish",
        tags=["diplomatik", "konsullik", "vakolatxona"],
        text="Xorijiy davlatlarning Oʻzbekiston Respublikasida akkreditatsiyadan oʻtgan "
             "diplomatik vakolatxonalari, konsullik muassasalari va ularga tenglashtirilgan "
             "tashkilotlar mobil qurilmalarni roʻyxatga olishning alohida (belgilangan) "
             "tartibidan foydalanadi.",
    ),
]
