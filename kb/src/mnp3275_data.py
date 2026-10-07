# -*- coding: utf-8 -*-
"""
3275-son "Telekommunikatsiya xizmatlarini ko'rsatish qoidalari" (30.06.2020) ning
MNP (abonent raqamini ko'chirish) qismi uchun qidiruv metama'lumotlari.

Normativ matn ``ingest_mnp3275.py`` tomonidan manbadan o'zgarishsiz olinadi; bu
modul faqat uni QIDIRILADIGAN qiladi:

* ``SELECTED`` — MNPga tegishli bandlar (10-§ to'liq: 167–226; shuningdek
  ta'riflar, shartnoma, operator/abonent huquq-majburiyatlari, to'lovlar bo'limidagi
  MNPga aloqador bandlar);
* ``EXCERPTS`` — faqat bir qismi MNPga tegishli bo'lgan bandlardan olinadigan
  xatboshilar (kalit so'z bo'yicha);
* ``SPLITS`` — mazmunan alohida qoidalarni o'z ichiga olgan uzun bandlarni alohida
  qidiriladigan qismlarga bo'lish (masalan 208-band: rouming qarzi oqimi);
* ``TITLES`` / ``PLAIN`` — mavzu sarlavhasi va oddiy tildagi qisqa izoh (legal
  matn o'zgarmaydi, izoh alohida birinchi qator bo'lib turadi);
* ``TAGS`` — real foydalanuvchi iboralari, RU/EN sinonimlari, texnik atamalar;
* ``CASE_TYPES`` — taxonomy.CASE_TYPES dagi ``mnp_*`` kalitlari;
* ``REJECTION_REASONS`` — rad sabablari: belgi / sabab / yechim / normativ asos.
"""

DOC_TITLE = "Telekommunikatsiya xizmatlarini koʻrsatish qoidalari (3275-son, 30.06.2020)"

# --- qaysi bandlar -------------------------------------------------------------------

# 3-band ta'riflaridan MNPga tegishlilari: (ta'rif boshlanishi, kalit)
DEFINITIONS = [
    ("abonent raqamining koʻchib oʻtishi", "kochib_otishi"),
    ("abonent raqami", "abonent_raqami"),
    ("abonent —", "abonent"),
    ("birlamchi operator", "birlamchi_operator"),
    ("koʻchib oʻtgan raqamlar markazlashtirilgan bazasi", "markazlashtirilgan_baza"),
    ("koʻchirilgan raqamlar markazlashtirilgan bazasi", "krmb"),
    ("KRMB operatori", "krmb_operatori"),
    ("koʻchirilgan raqamlarning lokal bazasini KRMB bilan sinxronlash", "sinxronlash"),
    ("koʻchirilgan raqamlarning lokal bazasi", "lokal_baza"),
    ("marshrut raqami", "rn"),
    ("operator (provayder)-donor", "donor"),
    ("operator (provayder)-retsipiyent", "retsipiyent"),
    ("xato koʻchirish", "xato_kochirish"),
    ("barcha chaqiruvlar uchun soʻrov", "all_call_query"),
    ("progressiv marshrutlash", "onward_routing"),
    ("MSISDN", "msisdn"),
    ("SIM/RUIM-karta", "sim"),
    ("eSIM", "esim"),
    ("qisqa matnli xabar (SMS)", "sms"),
    ("Oʻzbekiston Respublikasida jismoniy shaxsning shaxsiy identifikatsiya raqami", "jshshir"),
    ("rouming —", "rouming"),
    ("mahalliy operator", "mahalliy_operator"),
]

# Ta'rif sarlavhalari uchun qisqa, qidiriladigan nom (legal ta'rif matni o'zgarmaydi)
DEF_LABELS = {
    "kochib_otishi": "MNP — abonent raqamining koʻchib oʻtishi (raqamni boshqa operatorga koʻchirish)",
    "krmb": "KRMB — koʻchirilgan raqamlar markazlashtirilgan bazasi",
    "markazlashtirilgan_baza": "Koʻchib oʻtgan raqamlar markazlashtirilgan bazasi (KRMB)",
    "krmb_operatori": "KRMB operatori",
    "lokal_baza": "Koʻchirilgan raqamlarning lokal bazasi",
    "sinxronlash": "Lokal bazani KRMB bilan sinxronlash",
    "rn": "Marshrut raqami (routing number, RN)",
    "donor": "Donor — siz ketayotgan eski operator (operator-donor)",
    "retsipiyent": "Retsipiyent — siz oʻtayotgan yangi operator (operator-retsipiyent)",
    "birlamchi_operator": "Birlamchi operator",
    "xato_kochirish": "Xato koʻchirish",
    "all_call_query": "All Call Query (barcha chaqiruvlar uchun soʻrov)",
    "onward_routing": "Onward Routing (progressiv marshrutlash)",
}

# To'liq olinadigan bandlar
SELECTED = [str(n) for n in range(167, 227)] + [
    "19", "20", "256", "257", "258", "270", "339", "370", "371", "373",
]
# Faqat MNPga tegishli xatboshilari olinadigan bandlar (kalit so'z, normallashtirilmagan)
EXCERPTS = {
    "251": ["maʼlumotlar oʻzgarishi bilan bogʻliq oʻzgarishlar"],
    "296": ["markazlashtirilgan bazasiga ulanish", "donorga rouming xizmatlari",
            "koʻchib oʻtish xizmatidan foydalanish huquqiga", "yoʻqolganda abonentning",
            "qarzini va oldindan toʻlovning"],
    "318": ["koʻchib oʻtish xizmatidan foydalanishi"],
    "324": ["maʼlumotlar oʻzgargani haqida", "jismoniy shaxs uchun — familiyasi",
            "yuridik shaxs uchun — nomi", "abonent raqami koʻchib oʻtgan taqdirda"],
}

# Uzun bandlarni mazmuniy qismlarga bo'lish: band -> [(qism kaliti, sarlavha, xatboshi indekslari)]
SPLITS = {
    "179": [
        ("kanallar", "Talabnoma topshirish usullari (ofis, veb-sayt, mobil ilova)", [0, 1, 2, 3]),
        ("malumot_ozgarishi",
         "Shaxsiy maʼlumotlar oʻzgargan boʻlsa — avval donor shartnomasini yangilash", [4]),
    ],
    "183": [
        ("sorov", "Retsipiyentning KRMBga soʻrovi tarkibi (jismoniy va yuridik shaxs)",
         [0, 1, 2, 3, 4, 5, 6, 7]),
        ("toliq", "Toʻliq koʻchirish: bir nechta raqam — bittasi rad etilsa hammasi rad", [8]),
        ("qisman", "Qisman koʻchirish: tasdiqlangan raqamlar koʻchiriladi", [9]),
    ],
    "208": [
        ("aniqlash", "Rouming qarzi: donor 30 kalendar kun ichida hisob taqdim etishi mumkin",
         [0]),
        ("tolash_muddati", "Rouming qarzi: KRMB orqali soʻrov va 7 ish kunlik toʻlash muddati",
         [1]),
        ("krmb_tekshiruv", "Rouming qarzi: KRMB operatori 30 kunlik muddatni tekshiradi", [2]),
        ("xabarnoma", "Rouming qarzi: retsipiyent 15 daqiqa ichida SMS orqali xabar beradi",
         [3, 4, 5, 6]),
        ("cheklash", "Rouming qarzi 7 ish kunida toʻlanmasa: xizmat toʻxtatiladi", [7, 8]),
        ("blokdan_chiqarish", "Rouming qarzi toʻlanganda: 15 daqiqada blokdan chiqarish", [9]),
    ],
}

TITLES = {
    "167": "MNP xizmatini kim koʻrsatadi",
    "168": "MNP chastotasi: 30 kalendar kunda koʻpi bilan bir marta",
    "169": "Qaysi raqamlar koʻchiriladi; raqam terish formati oʻzgarmaydi",
    "170": "MNP xizmati raqamlarini mobil tarmoqqa va aksincha koʻchirish taqiqlanadi",
    "171": "KRMB operatorining vazifasi: axborotni avtomatlashtirish va muvofiqlashtirish",
    "172": "Barcha MNP axborot almashinuvi KRMB operatori orqali",
    "173": "KRMB shaxsga doir maʼlumotlar qonuniga rioya qilgan holda yuritiladi",
    "174": "Operatorlar KRMBga maʼlumot taqdim etadi",
    "175": "Operatorlarning KRMBdan foydalanishi shartnoma asosida",
    "176": "KRMBda qanday axborot saqlanadi",
    "177": "KRMB operatorining texnik tadbirlari",
    "178": "KRMBdagi axborotni muhofaza qilish",
    "180": "MNP muddati: talabnomadan keyin 8 ish soatidan koʻp emas",
    "181": "Retsipiyent vazifalari: talabnoma, yangi shartnoma, vaqtinchalik raqamli SIM",
    "182": "Vaqtinchalik SIM: koʻchirish tugaguncha va rad etilganda",
    "184": "KRMB tekshiruvi va rad etish: talabnoma, 30 kun, aktiv talabnoma",
    "185": "KRMB soʻrovni donorga yuboradi",
    "186": "Donor tekshiruvi va rad etish: shaxsiy maʼlumot, qarz, majburiyat",
    "187": "Donor talabnomani 3 ish soatida koʻrib chiqadi",
    "188": "Donor tasdigʻi — eski shartnomani bekor qilish asosi",
    "189": "Texnik koʻchirish boshlanishi haqida SMS",
    "190": "Texnik koʻchirish: retsipiyent va donor harakatlari",
    "191": "KRMB koʻchirishni qayd etadi va marshrutlashni oʻzgartirishni soʻraydi",
    "192": "Operatorlar marshrutlashni oʻzgartiradi",
    "193": "Koʻchirish muvaffaqiyatli tugaganligi haqida KRMB xabari",
    "194": "MNP muvaffaqiyatli tugaganini qanday bilaman: SMS xabar",
    "195": "MNPdan voz kechish (arizani bekor qilish) mumkin — donor tasdiqlaguncha",
    "196": "Avval koʻchirilgan raqamni yana koʻchirish (takroriy porting)",
    "197": "KRMB orqali barcha harakatlar sinxron tasdiqlanadi",
    "198": "Marshrutlash texnologiyalari: All Call Query va Onward Routing",
    "199": "Operatorning MNP boʻyicha majburiyatlari",
    "200": "KRMB operatorining majburiyatlari",
    "201": "Donor va retsipiyent faqat KRMB orqali oʻzaro ishlaydi",
    "202": "KRMBda jarayon avtomatlashtirilgan",
    "203": "MNP xarajatlari operatorlar hisobidan",
    "204": "MNP narxini retsipiyent belgilaydi",
    "205": "MNP toʻlovi bir martalik, retsipiyentga toʻlanadi",
    "206": "Operator va KRMB operatori hisob-kitoblari",
    "207": "Balansdagi pul: donor tomonidan qaytariladi",
    "209": "Retsipiyent bilan shartnoma bekor boʻlsa: raqam birlamchi operatorga qaytadi",
    "210": "Raqamni qaytarish shartlari",
    "211": "Raqam qaytarilishi haqida xabarnoma",
    "212": "Birlamchi operator raqam olinganini tasdiqlaydi",
    "213": "Xato koʻchirish aniqlansa: retsipiyent xabar beradi",
    "214": "Xato koʻchirishni qaytarish: KRMB tekshiruvi",
    "215": "Donor xato koʻchirilgan raqam soʻrovini tekshiradi",
    "216": "Xato koʻchirishni qaytarish: abonent arizasi, toʻlovsiz",
    "217": "Donor xato koʻchirilgan raqamni qaytarishni soʻraydi",
    "218": "Xato koʻchirish soʻrovini KRMB tekshiradi",
    "219": "Xato koʻchirish soʻrovi tasdiqlanganda",
    "220": "Xato koʻchirish soʻrovi rad etilganda",
    "221": "Operator xato koʻchirishni qaytarishni tasdiqlaydi yoki rad etadi",
    "222": "30 daqiqada javob boʻlmasa — avtomatik tasdiq",
    "223": "Donor 30 daqiqa ichida xizmatni qayta yoqadi",
    "224": "Xato koʻchirilgan raqam deaktivatsiyasi va marshrutlash",
    "225": "Marshrutlashni 30 daqiqada oʻzgartirish, 1 soatda tasdiqlash",
    "226": "Xato koʻchirishdan keyin xizmatlar, tarif va balans tiklanadi",
    "19": "Abonent maʼlumotlarini uchinchi shaxslarga berish taqiqlanadi",
    "20": "Abonentlar bazalari konfidensial himoyalanadi",
    "251": "Shartnomadagi shaxsiy maʼlumotni oʻzgartirish bepul",
    "256": "Shartnoma bekor boʻlish holatlari, jumladan raqam koʻchib oʻtganda",
    "257": "Shartnoma bekor boʻlganda hisob-kitoblar",
    "258": "Raqamni (shartnomani) boshqa shaxs nomiga oʻtkazish",
    "270": "Mobil shartnoma: shaxsan yoki ishonchnomali vakil orqali",
    "296": "Mobil operatorning MNPga oid majburiyatlari",
    "318": "Abonentning MNP xizmatidan foydalanish huquqi",
    "324": "Abonent majburiyatlari: maʼlumot oʻzgarishi, donor oldidagi qarz",
    "339": "Shartnoma bekor boʻlganda avans qoldigʻi 15 kunda qaytariladi",
    "370": "Qoida buzilganda xizmat toʻxtatilishi",
    "371": "Buzilish bartaraf etilgach xizmat tiklanadi",
    "373": "MNP toʻlovi va retsipiyent bilan shartnoma",
}

# Oddiy tildagi qisqa izoh (bandning legal matni o'zgarmaydi; izoh alohida qator)
PLAIN = {
    "def:kochib_otishi": "Oddiy tilda: MNP — telefon raqamingizni saqlagan holda boshqa mobil "
                         "operatorga oʻtish. Raqam oʻsha qoladi, operator oʻzgaradi.",
    "def:donor": "Oddiy tilda: donor — siz ketayotgan eski operator.",
    "def:retsipiyent": "Oddiy tilda: retsipiyent — siz oʻtayotgan yangi operator.",
    "def:birlamchi_operator": "Oddiy tilda: birlamchi operator — raqam dastlab ajratilgan "
                              "(raqam aslida tegishli boʻlgan) operator.",
    "def:krmb": "Oddiy tilda: KRMB — koʻchirilgan raqamlarning markaziy bazasi; operatorlar "
                "MNP soʻrovlarini shu orqali almashadi va qoʻngʻiroqlar toʻgʻri operatorga "
                "yetadi.",
    "def:krmb_operatori": "Oddiy tilda: KRMB operatori — markaziy MNP bazasini yurituvchi "
                          "tashkilot.",
    "def:lokal_baza": "Oddiy tilda: har bir operatordagi KRMB nusxasi; qoʻngʻiroqni koʻchgan "
                      "raqamga toʻgʻri yoʻnaltirish uchun ishlatiladi.",
    "def:sinxronlash": "Oddiy tilda: operatorning lokal bazasi markaziy KRMB bilan muntazam "
                       "yangilab turiladi.",
    "def:rn": "Oddiy tilda: RN — koʻchgan raqamga qoʻngʻiroqni yangi operatorga yoʻnaltirish "
              "uchun ishlatiladigan texnik manzil.",
    "def:all_call_query": "Oddiy tilda: qoʻngʻiroq qiluvchi tarmoq har bir chaqiruvda bazadan "
                          "raqam qaysi operatorda ekanini soʻraydi va toʻgʻridan-toʻgʻri "
                          "yoʻnaltiradi.",
    "def:onward_routing": "Oddiy tilda: qoʻngʻiroq avval donor (eski operator) tarmogʻiga "
                          "boradi, u bazadan tekshirib, yangi operatorga uzatadi.",
    "def:xato_kochirish": "Oddiy tilda: abonent soʻramagan holda xodim xatosi bilan raqam "
                          "(masalan, talabnomadagidan boshqa raqam) koʻchirib yuborilishi.",
    "168": "Oddiy tilda: raqamni 30 kalendar kun ichida faqat bir marta koʻchirish mumkin.",
    "169": "Oddiy tilda: faqat mobil raqamlar koʻchiriladi va raqamingiz shakli oʻzgarmaydi.",
    "180": "Oddiy tilda: talabnomadan keyin koʻchirish 8 ish soatidan oshmasligi kerak.",
    "181": "Oddiy tilda: yangi operator talabnomangizni qabul qiladi, yangi shartnoma tuzadi va "
           "vaqtinchalik raqamli yangi SIM beradi (eSIM ham boʻlishi mumkin).",
    "182": "Oddiy tilda: vaqtinchalik SIM darhol ishlaydi; koʻchirish rad etilsa ham undan "
           "foydalanishda davom etasiz.",
    "184": "Oddiy tilda: markaziy baza (KRMB) arizani rad etadi, agar u notoʻgʻri toʻldirilgan "
           "boʻlsa, oxirgi koʻchirishdan 30 kun oʻtmagan boʻlsa yoki shu raqam boʻyicha boshqa "
           "aktiv ariza boʻlsa. Rad sababi vaqtinchalik SIMga SMS bilan yuboriladi.",
    "186": "Oddiy tilda: eski operator rad etadi, agar shaxsiy maʼlumotlaringiz uning "
           "shartnomasiga mos kelmasa, unga qarzingiz boʻlsa (roumingdan tashqari) yoki "
           "bajarilmagan majburiyatingiz boʻlsa. Rad sababi SMS bilan keladi.",
    "187": "Oddiy tilda: eski operator arizani 3 ish soatida koʻrib chiqishi kerak; "
           "kechiksa, koʻchirishga ruxsat avtomatik beriladi.",
    "189": "Oddiy tilda: texnik koʻchirish boshlanganda vaqtinchalik SIMga SMS keladi.",
    "194": "Oddiy tilda: MNP muvaffaqiyatli tugaganda yangi operator koʻchirilgan raqamli "
           "SIMingizga SMS yuboradi.",
    "195": "Oddiy tilda: eski operator soʻrovni tasdiqlaguncha MNPdan voz kechishingiz "
           "(arizani bekor qilishingiz) mumkin.",
    "196": "Oddiy tilda: koʻchirilgan raqamni yana boshqa operatorga (yoki eskisiga) "
           "koʻchirish xuddi shu tartibda boʻladi; 30 kunlik cheklov amal qiladi.",
    "198": "Oddiy tilda: qoʻngʻiroqlar koʻchgan raqamga All Call Query yoki Onward Routing "
           "usulida yoʻnaltiriladi.",
    "204": "Oddiy tilda: MNP narxini yangi operator oʻzi belgilaydi.",
    "205": "Oddiy tilda: MNP uchun bir marta, yangi operatorga, shartnoma tuzishda toʻlanadi.",
    "207": "Oddiy tilda: eski raqam hisobidagi sarflanmagan pul yangi operatorga "
           "oʻtmaydi — uni eski operator (donor) qaytaradi.",
    "209": "Oddiy tilda: yangi operator bilan shartnoma bekor qilinsa, raqam bir ish kunida "
           "uning asl operatoriga qaytariladi.",
    "216": "Oddiy tilda: raqamingiz xato koʻchirilgan boʻlsa, eski operatorga yozma ariza "
           "yoki maʼlumot xizmati orqali murojaat qiling; qaytarish uchun pul olinmaydi.",
    "226": "Oddiy tilda: xato koʻchirishdan keyin xizmatlar, tarif va balans avvalgi holatiga "
           "tiklanadi.",
    "258": "Oddiy tilda: raqamni boshqa odam nomiga oʻtkazish uchun u ham ishtirok etishi va "
           "rozi boʻlishi kerak; eski shartnoma bekor qilinib, yangisi tuziladi.",
    "270": "Oddiy tilda: mobil shartnoma (MNPda yangi operator bilan ham) faqat shaxsan yoki "
           "ishonchnomali vakil orqali tuziladi.",
    "339": "Oddiy tilda: shartnoma bekor boʻlganda avans qoldigʻini qaytarish uchun operatorga "
           "murojaat qilasiz; u 15 kun ichida qaytarishi shart.",
    "179#kanallar": "Oddiy tilda: MNP arizasini yangi operatorning ofisida (pasport bilan), "
                    "rasmiy veb-saytida yoki mobil ilovasida berish mumkin.",
    "179#malumot_ozgarishi": "Oddiy tilda: familiya yoki pasport oʻzgargan boʻlsa, MNP "
                             "arizasidan OLDIN eski operatordagi shartnomangizni yangilang, "
                             "aks holda maʼlumotlar mos kelmaydi deb rad etiladi.",
    "183#toliq": "Oddiy tilda: bir nechta raqamni 'toʻliq' koʻchirishda bittasi rad etilsa, "
                 "butun roʻyxat rad etiladi.",
    "183#qisman": "Oddiy tilda: 'qisman' koʻchirishda rad etilgan raqamlar qoladi, eski "
                  "operator tasdiqlagan raqamlar koʻchiriladi.",
    "208#aniqlash": "Oddiy tilda: koʻchirishdan keyin ham eski operator rouming qarzini "
                    "koʻchirish sanasidan 30 kalendar kun ichida talab qilishi mumkin.",
    "208#tolash_muddati": "Oddiy tilda: rouming qarzini toʻlash muddati 7 ish kunidan "
                          "oshmaydi.",
    "208#xabarnoma": "Oddiy tilda: yangi operator 15 daqiqa ichida SMS bilan rouming qarzini "
                     "toʻlash kerakligini xabar qiladi.",
    "208#cheklash": "Oddiy tilda: 7 ish kunida toʻlanmasa, yangi operator qarz toʻlanguncha "
                    "xizmatni toʻxtatadi.",
    "208#blokdan_chiqarish": "Oddiy tilda: qarz toʻlangach eski operator 15 daqiqa ichida "
                             "blokdan chiqarish haqida xabar beradi.",
}

_REJECT = ["mnp rad etildi", "ko'chirish rad etildi", "raqam ko'chmadi", "rad sababi",
           "перенос номера отклонен", "отказ в переносе", "number porting rejected",
           "why was mnp rejected"]

TAGS = {
    "def:kochib_otishi": ["mnp nima", "mnp", "raqamni boshqa operatorga o'tkazish",
                          "operator almashtirish", "raqam saqlanadi", "что такое mnp",
                          "перенос номера", "what is mnp", "mobile number portability",
                          "number portability"],
    "def:donor": ["donor nima", "donor operator", "eski operator", "оператор-донор",
                  "что такое оператор донор", "donor operator", "what is the donor operator"],
    "def:retsipiyent": ["retsipiyent nima", "retsipient", "recipient", "yangi operator",
                        "оператор-реципиент", "что такое оператор реципиент",
                        "recipient operator", "what is the recipient operator"],
    "def:birlamchi_operator": ["birlamchi operator", "asl operator", "первичный оператор",
                               "original operator"],
    "def:krmb": ["krmb nima", "krmb", "ko'chirilgan raqamlar bazasi", "markazlashtirilgan baza",
                 "что такое krmb", "центральная база перенесенных номеров",
                 "centralized number portability database", "what is krmb"],
    "def:markazlashtirilgan_baza": ["krmb", "markazlashtirilgan baza", "central database"],
    "def:krmb_operatori": ["krmb operatori", "krmb kim boshqaradi", "оператор krmb",
                           "krmb operator"],
    "def:lokal_baza": ["lokal baza", "local database", "локальная база"],
    "def:sinxronlash": ["sinxronlash", "synchronization", "синхронизация"],
    "def:rn": ["rn", "routing number", "marshrut raqami", "маршрутный номер"],
    "def:all_call_query": ["all call query", "acq", "marshrutlash"],
    "def:onward_routing": ["onward routing", "progressiv marshrutlash"],
    "def:xato_kochirish": ["xato ko'chirish nima", "raqamimni men so'ramasdan ko'chirishdi",
                           "noto'g'ri raqam ko'chib ketdi", "wrong number ported",
                           "номер перенесли по ошибке", "ruxsatsiz ko'chirish"],
    "def:msisdn": ["msisdn", "telefon raqami"],
    "def:abonent_raqami": ["abonent raqami nima", "номер абонента"],
    "167": ["mnp xizmati kim ko'rsatadi", "operatorlar"],
    "168": ["bir oyda ikki marta", "30 kunda bir marta", "qayta ko'chirish", "takroriy porting",
            "operatorni tez-tez almashtirish", "как часто можно переносить номер",
            "once in 30 days", "how often can i port"],
    "169": ["raqam o'zgaradimi", "raqam shakli", "raqam formati", "номер не меняется",
            "does my number change"],
    "176": ["krmb nima saqlaydi", "krmb ma'lumotlari"],
    "177": ["krmb kechayu kunduz", "krmb muhofaza"],
    "178": ["krmb ma'lumotlarini himoya qilish", "ruxsatsiz kirish", "data protection"],
    "180": ["mnp qancha vaqtda", "necha soatda ko'chadi", "8 ish soati", "ko'chirish muddati",
            "сколько занимает перенос номера", "how long does number porting take"],
    "181": ["yangi sim", "vaqtincha raqam", "vaqtinchalik raqam", "esim", "yangi shartnoma",
            "новая sim карта", "temporary number", "new sim"],
    "182": ["vaqtincha raqamli sim", "rad etilsa sim", "временный номер"],
    "184": _REJECT + ["30 kun o'tmagan", "aktiv talabnoma", "noto'g'ri to'ldirilgan"],
    "186": _REJECT + ["ma'lumotlarim mos emas", "qarzdorlik", "majburiyat", "eski operatorga qarz",
                      "несоответствие данных", "долг перед оператором"],
    "187": ["donor necha soatda ko'rib chiqadi", "3 ish soati", "donor muddati",
            "срок рассмотрения донором"],
    "188": ["eski shartnoma bekor", "shartnoma bekor qilish"],
    "189": ["texnik ko'chirish boshlandi sms"],
    "193": ["ko'chirish tugadi", "muvaffaqiyatli"],
    "194": ["mnp tugaganini qanday bilaman", "muvaffaqiyatli tugadi", "sms keladi",
            "mnp bo'ldimi", "как узнать что номер перенесен", "porting completed sms",
            "how do i know porting is done"],
    "195": ["mnp arizasini bekor qilish", "fikrimdan qaytdim", "portingni to'xtatmoqchiman",
            "mnpdan voz kechish", "отменить перенос номера", "можно ли отменить перенос",
            "cancel number porting", "cancel a porting request"],
    "196": ["eski operatorga qaytish", "qayta ko'chirish", "takroriy porting",
            "вернуться к старому оператору", "port back"],
    "198": ["all call query", "onward routing", "marshrutlash", "routing"],
    "199": ["operator majburiyatlari mnp", "lokal baza"],
    "200": ["krmb operatori majburiyatlari", "sinxronlash", "ruxsatsiz foydalanishdan himoya"],
    "201": ["donor va retsipiyent krmb orqali"],
    "202": ["avtomatik rejim", "krmb avtomatik"],
    "204": ["mnp narxi", "mnp qancha turadi", "стоимость переноса номера", "mnp price"],
    "205": ["mnp to'lovi", "bir martalik to'lov", "оплата переноса"],
    "207": ["balansim yangi operatorga o'tadimi", "eski simda pulim qolgan",
            "mnp qildim pulim nima bo'ladi", "balansdagi pul", "qoldiq mablag'",
            "переносится ли баланс при mnp", "переносится ли баланс",
            "does my balance move to the new operator", "balance transfer"],
    "209": ["shartnoma bekor bo'lsa raqam", "raqam qaytariladi", "birlamchi operatorga qaytarish",
            "что будет с номером при расторжении", "number returned"],
    "210": ["raqamni qaytarish"],
    "213": ["xato ko'chirish", "wrong port"],
    "214": ["xato ko'chirish qaytarish"],
    "216": ["xato ko'chirilgan raqamni qaytarish", "raqamimni so'ramasdan ko'chirishdi",
            "xato ko'chirish to'lovsiz", "номер перенесли по ошибке", "wrong number ported"],
    "222": ["30 daqiqa"],
    "223": ["xizmatni aktivatsiya qilish"],
    "226": ["xato ko'chirishdan keyin balans tiklanadi", "tarif tiklanadi"],
    "19": ["shaxsiy ma'lumotlar himoyasi", "персональные данные"],
    "20": ["konfidensial baza"],
    "251": ["shartnomadagi ma'lumotni o'zgartirish bepul", "pasport almashgan"],
    "256": ["raqam ko'chganda shartnoma bekor", "shartnoma bekor qilish"],
    "258": ["raqamni boshqa shaxs nomiga o'tkazish", "qayta rasmiylashtirish",
            "переоформление номера", "transfer number to another person"],
    "270": ["otamning raqamini ko'chirib bera olamanmi", "boshqa odam nomidagi raqam",
            "ishonchnoma", "vakil", "raqam egasi", "доверенность", "power of attorney",
            "someone else's number"],
    "296": ["operator mnpga to'sqinlik qilmaydi", "rouming qarzi xizmat to'xtatish", "krmbga ulanish"],
    "318": ["mnp huquqi", "право на перенос номера"],
    "324": ["ma'lumot o'zgarsa 15 kun", "donor oldidagi qarzni to'lash", "familiya o'zgardi"],
    "339": ["pulni qaytarish 15 kun", "avans qaytarish", "возврат аванса"],
    "373": ["mnp to'lovi"],
    "179#kanallar": ["mnp arizasini qayerda topshirish", "ariza berish", "talabnoma", "veb-sayt",
                     "mobil ilova", "где подать заявление на перенос", "where to apply for mnp"],
    "179#malumot_ozgarishi": ["ma'lumotlarim mos emas deyapti", "familiya o'zgargan",
                              "pasport almashgan", "shaxsiy ma'lumot o'zgargan",
                              "данные не совпадают", "personal data mismatch"],
    "183#sorov": ["krmb so'rovi", "pasport ma'lumotlari", "stir"],
    "183#toliq": ["bir nechta raqamni ko'chirish", "to'liq ko'chirish", "full porting",
                  "несколько номеров", "korporativ raqamlar"],
    "183#qisman": ["qisman ko'chirish", "partial porting", "bir nechta raqam"],
    "208#aniqlash": ["mnpdan keyin rouming qarzi", "rouming qarzi", "rouming qarzi chiqdi",
                     "eski operator qancha vaqt ichida rouming qarzini talab qilishi mumkin",
                     "долг за роуминг после переноса", "roaming debt after porting"],
    "208#tolash_muddati": ["rouming qarzini necha kunda to'lash kerak", "7 ish kuni",
                           "qarzni to'lash muddati", "срок оплаты долга за роуминг",
                           "roaming debt payment deadline"],
    "208#krmb_tekshiruv": ["rouming qarzi 30 kun tekshiruvi"],
    "208#xabarnoma": ["rouming qarzi sms", "qarz haqida xabar", "уведомление о долге"],
    "208#cheklash": ["rouming qarzi sabab bloklandi", "xizmat to'xtatildi", "qarz to'lanmasa",
                     "заблокировали за долг роуминга"],
    "208#blokdan_chiqarish": ["qarzni to'ladim blokdan chiqarish", "unblock after payment"],
}

CASE_TYPES = {
    "def:kochib_otishi": "mnp_definition", "def:donor": "mnp_definition",
    "def:retsipiyent": "mnp_definition", "def:birlamchi_operator": "mnp_definition",
    "def:abonent": "mnp_definition", "def:abonent_raqami": "mnp_definition",
    "def:msisdn": "mnp_definition", "def:sim": "mnp_definition", "def:esim": "mnp_definition",
    "def:sms": "mnp_definition", "def:jshshir": "mnp_definition",
    "def:rouming": "mnp_definition", "def:mahalliy_operator": "mnp_definition",
    "def:krmb": "mnp_krmb", "def:krmb_operatori": "mnp_krmb",
    "def:markazlashtirilgan_baza": "mnp_krmb", "def:lokal_baza": "mnp_krmb",
    "def:sinxronlash": "mnp_krmb", "def:rn": "mnp_routing",
    "def:all_call_query": "mnp_routing", "def:onward_routing": "mnp_routing",
    "def:xato_kochirish": "mnp_wrong_port",
    "167": "mnp_application", "168": "mnp_repeat_porting", "169": "mnp_eligibility",
    "170": "mnp_eligibility", "180": "mnp_timing", "181": "mnp_application",
    "182": "mnp_application", "184": "mnp_rejection", "185": "mnp_application",
    "186": "mnp_rejection", "187": "mnp_timing", "188": "mnp_success", "189": "mnp_success",
    "190": "mnp_success", "191": "mnp_routing", "192": "mnp_routing", "193": "mnp_success",
    "194": "mnp_success", "195": "mnp_cancel", "196": "mnp_repeat_porting",
    "197": "mnp_krmb", "198": "mnp_routing", "199": "mnp_application", "200": "mnp_krmb",
    "201": "mnp_krmb", "202": "mnp_krmb", "203": "mnp_price", "204": "mnp_price",
    "205": "mnp_price", "206": "mnp_price", "207": "mnp_balance",
    "209": "mnp_number_return", "210": "mnp_number_return", "211": "mnp_number_return",
    "212": "mnp_number_return",
    "19": "mnp_data_protection", "20": "mnp_data_protection", "251": "mnp_identity_mismatch",
    "256": "mnp_number_return", "257": "mnp_balance", "258": "mnp_ownership",
    "270": "mnp_ownership", "296": "mnp_application", "318": "mnp_application",
    "324": "mnp_identity_mismatch", "339": "mnp_balance", "370": "mnp_blocked_number",
    "371": "mnp_blocked_number", "373": "mnp_price",
    "179#kanallar": "mnp_application", "179#malumot_ozgarishi": "mnp_identity_mismatch",
    "183#sorov": "mnp_application", "183#toliq": "mnp_multi_number",
    "183#qisman": "mnp_multi_number",
    "208#aniqlash": "mnp_roaming_debt", "208#tolash_muddati": "mnp_roaming_debt",
    "208#krmb_tekshiruv": "mnp_roaming_debt", "208#xabarnoma": "mnp_roaming_debt",
    "208#cheklash": "mnp_roaming_debt", "208#blokdan_chiqarish": "mnp_roaming_debt",
}
for _n in range(171, 179):
    CASE_TYPES.setdefault(str(_n), "mnp_krmb")
for _n in range(213, 227):
    CASE_TYPES.setdefault(str(_n), "mnp_wrong_port")

# --- rad etish sabablari: belgi / sabab / yechim / normativ asos ----------------------------
REJECTION_REASONS = [
    {
        "id": "notogri_talabnoma",
        "title": "MNP rad etildi: talabnoma notoʻgʻri toʻldirilgan",
        "case_type": "mnp_rejection",
        "symptom": "SMSda talabnoma notoʻgʻri yoki toʻliq toʻldirilmaganligi aytiladi.",
        "cause": "KRMB operatori soʻrovning talabnomaga muvofiq toʻgʻri va aniq "
                 "toʻldirilganligini tekshiradi; shart bajarilmasa talabnoma rad etiladi.",
        "resolution": ["Yangi operator (retsipiyent) kamchiliklarni bartaraf etadi",
                       "Retsipiyent KRMB operatoriga yangi soʻrov yuboradi"],
        "legal_refs": ["3275-son Qoidalar, 184-band"],
        "tags": ["ariza noto'g'ri to'ldirilgan", "talabnoma xato", "заявление заполнено неверно"],
    },
    {
        "id": "malumot_mos_emas",
        "title": "MNP rad etildi: shaxsiy maʼlumotlar eski operator maʼlumotiga mos emas",
        "case_type": "mnp_identity_mismatch",
        "symptom": "\"Maʼlumotlar mos emas\" degan rad sababi keladi.",
        "cause": "Donor KRMBdan kelgan shaxsiy maʼlumotlar (F.I.Sh., pasport, raqam egasi) "
                 "u bilan tuzilgan shartnomadagi maʼlumotlarga mos kelishini tekshiradi.",
        "resolution": [
            "Eski operatorga (donor) murojaat qilib, shartnomadagi maʼlumotlarni yangilang "
            "(familiya oʻzgargan, pasport almashgan va h.k.) — bu bepul",
            "Shundan keyin MNP arizasini qayta topshiring",
            "Chatda pasport yoki JSHSHIR yuborish shart emas — tekshiruv operator ofisida boʻladi",
        ],
        "legal_refs": ["3275-son Qoidalar, 179-band (oxirgi xatboshi)", "186-band",
                       "251-band", "324-band b)"],
        "tags": ["ma'lumotlarim mos emas deyapti", "ma'lumotlar mos emas", "familiya o'zgargan",
                 "pasport almashgan", "данные не совпадают", "personal data mismatch"],
    },
    {
        "id": "30_kun",
        "title": "MNP rad etildi: oxirgi koʻchirishdan 30 kun oʻtmagan",
        "case_type": "mnp_repeat_porting",
        "symptom": "Yaqinda raqam koʻchirilgan va yana ariza berilgan.",
        "cause": "Raqam 30 kalendar kun ichida koʻpi bilan bir marta koʻchiriladi "
                 "(xato koʻchirish holatlari bundan mustasno).",
        "resolution": ["30 kalendar kun oʻtishini kuting", "Keyin arizani qayta topshiring"],
        "legal_refs": ["3275-son Qoidalar, 168-band", "184-band"],
        "tags": ["30 kun o'tmagan", "bir oyda ikki marta", "too soon to port again"],
    },
    {
        "id": "aktiv_talabnoma",
        "title": "MNP rad etildi: shu raqam boʻyicha aktiv talabnoma mavjud",
        "case_type": "mnp_rejection",
        "symptom": "Raqam boʻyicha boshqa koʻchirish arizasi hali yakunlanmagan.",
        "cause": "KRMB operatori raqam boʻyicha aktiv talabnomalar yoʻqligini tekshiradi.",
        "resolution": ["Avvalgi talabnoma yakunlanishini kuting yoki undan voz keching "
                       "(donor tasdiqlaguncha voz kechish mumkin)",
                       "Keyin yangi ariza bering"],
        "legal_refs": ["3275-son Qoidalar, 184-band", "195-band"],
        "tags": ["aktiv ariza bor", "ikkita ariza", "активная заявка"],
    },
    {
        "id": "qarzdorlik",
        "title": "MNP rad etildi: eski operator oldida qarzdorlik bor",
        "case_type": "mnp_debt",
        "symptom": "Rad sababi sifatida qarzdorlik koʻrsatiladi.",
        "cause": "Donor tekshirish paytida abonentning shartnoma boʻyicha qarzi yoʻqligini "
                 "tekshiradi (rouming xizmatlaridan tashqari).",
        "resolution": ["Eski operator oldidagi qarzni yoping",
                       "Shundan keyin koʻchirish uchun qayta ariza bering "
                       "(oʻsha retsipiyentga takroran berilganda yangi shartnoma shart emas)"],
        "legal_refs": ["3275-son Qoidalar, 186-band", "182-band", "324-band k)"],
        "tags": ["qarzdorlik sabab rad bo'ldi", "eski operatorga qarzim bor",
                 "eski operatorga qarzim bor mnp bo'ladimi", "qarz bor", "долг перед оператором",
                 "debt to old operator"],
    },
    {
        "id": "majburiyat",
        "title": "MNP rad etildi: donor bilan bajarilmagan majburiyat bor",
        "case_type": "mnp_rejection",
        "symptom": "Rad sababi sifatida shartnoma boʻyicha majburiyat koʻrsatiladi.",
        "cause": "Donor abonentda u bilan tuzilgan shartnoma boʻyicha majburiyatlar "
                 "yoʻqligini tekshiradi.",
        "resolution": ["Eski operator bilan majburiyatni (shartnoma shartini) aniqlab, "
                       "uni bajaring", "Keyin arizani qayta topshiring"],
        "legal_refs": ["3275-son Qoidalar, 186-band"],
        "tags": ["majburiyat bor", "shartnoma majburiyati", "обязательства перед оператором"],
    },
    {
        "id": "bloklangan",
        "title": "Raqam bloklangan boʻlsa MNP (3275-son Qoidalarda alohida rad sababi emas)",
        "case_type": "mnp_blocked_number",
        "symptom": "Raqam eski operator tomonidan bloklangan (SIM yoʻqolgan, toʻlov "
                   "qilinmagan, sud qarori va h.k.).",
        "cause": "3275-son Qoidalarda \"raqam bloklangan\" alohida rad asosi sifatida "
                 "koʻrsatilmagan; blok odatda qarz yoki bajarilmagan majburiyat bilan bogʻliq "
                 "(186-band) yoki SIM yoʻqolgani sababli (296-band). Tasdiqlangan FAQ "
                 "(KB-MNP-013) boʻyicha avval blokdan chiqarish kerak.",
        "resolution": ["Eski operatorga murojaat qilib, blok sababini aniqlang va "
                       "raqamni blokdan chiqaring (qarzni yopish, SIMni tiklash)",
                       "Keyin MNP arizasini qayta topshiring"],
        "legal_refs": ["3275-son Qoidalar, 186-band", "296-band", "370-371-band",
                       "KB-MNP-013 (FAQ)"],
        "tags": ["raqam bloklangan bo'lsa ko'chirish mumkinmi", "bloklangan raqam",
                 "sim yo'qolgan", "заблокированный номер перенос", "blocked number porting"],
    },
]
