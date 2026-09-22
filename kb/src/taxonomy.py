# -*- coding: utf-8 -*-
"""
Murojaatlar bilim bazasi uchun taksonomiya.
Kategoriyalar hujjat nomlari va matn ichidagi kalit so'zlardan aniqlanadi.
"""

# --- 1-daraja: mavzu (domain) -------------------------------------------------
DOMAINS = {
    "imei": "IMEI-kodlarni ro'yxatga olish (UZIMEI)",
    "mnp": "Abonent raqamini ko'chirish (MNP)",
    "murojaat_tartibi": "Murojaatlar bilan ishlash tartibi (ЎРҚ-445)",
    "aloqa_sifati": "Aloqa sifati va tarmoq masalalari",
    "boshqa": "Boshqa masalalar",
}

# --- 2-daraja: kazus turi (case_type) ----------------------------------------
# kalit -> (tavsif, kalit so'zlar)
CASE_TYPES = {
    "klon_imei": (
        "Klonlangan IMEI-kod aniqlangan qurilma",
        ["klonlangan", "klon", "клонированн", "dublikat imei"],
    ),
    "aniqlanmagan_imei": (
        "IMEI-kod aniqlanmagan / GSMA bazasida yo'q",
        ["aniqlanmagan", "не определен", "gsma", "tac raqami"],
    ),
    "bojxona": (
        "Bojxona kirim orderi / bojsiz olib kirish me'yori",
        ["bojxona", "kirim orderi", "таможен", "deklaratsiya", "bojsiz"],
    ),
    "royxatdan_otkazish": (
        "IMEI-kodni ro'yxatdan o'tkazish tartibi va muddati",
        ["ro‘yxatdan o‘tkaz", "ro'yxatga ol", "30 kalendar", "60 kalendar"],
    ),
    "tolov_tarif": (
        "Ro'yxatga olish to'lovi va tariflar",
        ["tarif", "bazaviy hisoblash", "to‘lov", "payme", "click", "upay"],
    ),
    "blokdan_chiqarish": (
        "Qurilma/raqamni blokdan chiqarish",
        ["blokdan", "qora ro‘yxat", "bloklangan", "разблок"],
    ),
    "eski_qurilma": (
        "Eski / ikkinchi qo'ldan olingan qurilma",
        ["eski tel", "ishlatilgan", "avtomatik ro‘yxatdan o‘tish davri"],
    ),
    "esim_ikkinchi_slot": (
        "E-SIM yoki ikkinchi IMEI sloti",
        ["e-sim", "esim", "ikkinchi imei", "ikkinchi slot"],
    ),
    "yoqotilgan_ogirlangan": (
        "Qurilma yo'qolgan yoki o'g'irlangan",
        ["yo‘qotil", "o‘g‘irla", "утер", "украден"],
    ),
    "mnp_ariza_rad": (
        "MNP arizasi rad etilgan",
        ["rad etil", "qarzdorlik", "mos kelmaydi", "отказ"],
    ),
    "mnp_tartib": (
        "MNP xizmatidan foydalanish tartibi",
        ["ko‘chirish", "mnp", "operatorni almash"],
    ),
    "taklif": (
        "Taklif (tizimni takomillashtirish bo'yicha)",
        ["taklif", "предложени"],
    ),
    "shikoyat": (
        "Shikoyat (buzilgan huquqni tiklash talabi)",
        ["shikoyat", "norozi", "жалоба"],
    ),
    "dop_soro v": (
        "Qo'shimcha ma'lumot so'ralgan (DOP)",
        ["qo‘shimcha ma’lumot", "dop"],
    ),
    "boshqa": ("Tasniflanmagan", []),
}

# --- 3-daraja: natija (outcome) ----------------------------------------------
OUTCOMES = {
    "ijobiy_hal": ("Masala ijobiy hal qilindi", ["ijobiy hal qilin", "ijobiy hal bo‘l"]),
    "tushuntirish": ("Tushuntirish berildi", ["tushuntirish beril", "tushuntirildi", "izoh beril"]),
    "etiroz_yoq": ("Murojaatchi e'tiroz bildirmagan", ["e’tirozingiz yo‘q", "eʼtirozingiz yo‘q", "etirozingiz yo'q"]),
    "muammo_yoq": ("Muammo aniqlanmadi", ["muammo aniqlanmadi", "muammo yo‘q", "kamchilik aniqlanmadi"]),
    "boglanib_bolmadi": ("Murojaatchi bilan bog'lanib bo'lmadi", ["bog‘lanib bo‘lmadi", "javob bermadi", "tushib bo‘lmadi"]),
    "rad": ("Talab qanoatlantirilmadi", ["qanoatlantirilmadi", "rad etildi"]),
    "boshqa": ("Aniqlanmagan", []),
}

# --- Metadata sxemasi ---------------------------------------------------------
CHUNK_SCHEMA = {
    "id": "str — barqaror chunk identifikatori (sha1)",
    "doc_id": "str — manba hujjat identifikatori",
    "source_type": "enum — qonun | nizom | faq | javob_xati | ichki_qoida",
    "source_title": "str — manba nomi",
    "authority": "int — 1 (qonun/VMQ) … 4 (amaliyot namunasi). Retrieval'da ustuvorlik.",
    "domain": "enum — DOMAINS kaliti",
    "case_type": "enum — CASE_TYPES kaliti",
    "outcome": "enum — OUTCOMES kaliti (faqat javob xatlari uchun)",
    "lang": "enum — uz_latn | uz_cyrl | ru",
    "text": "str — maskalangan chunk matni",
    "text_norm": "str — qidiruv uchun normallashtirilgan variant",
    "legal_refs": "list[str] — havola qilingan normativ hujjatlar (778-son VMQ, ЎРҚ-445 28-modda, …)",
    "valid_from": "str|null — normaning kuchga kirish sanasi",
    "pii_masked": "bool — maskalash bajarilgan",
    "pii_hits": "dict — qaysi turdagi PII nechta o'rinda maskalangan",
    "n_tokens": "int — taxminiy token soni",
}
