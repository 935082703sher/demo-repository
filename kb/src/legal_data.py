# -*- coding: utf-8 -*-
"""
Normativ baza — bilim bazasining eng yuqori ishonch darajasidagi qatlami
(authority = 1). Assistent javob berganda avval shu qatlamdan iqtibos keltiradi.

Manba: «Жисмоний ва юридик шахсларнинг мурожаатлари тўғрисида»ги
O‘zR Qonuni, ЎРҚ-445, 11.09.2017 (yangi tahrir), keyingi o‘zgartirishlar bilan
(ЎРҚ-608 10.03.2020, ЎРҚ-683 21.04.2021, ЎРҚ-963 20.09.2024, ЎРҚ-1144 07.05.2026).
"""

LAW = [
 dict(art="3-modda", title="Asosiy tushunchalar",
   text="Ariza — huquqlarni, erkinliklarni va qonuniy manfaatlarni amalga oshirishda "
        "yordam ko‘rsatish to‘g‘risidagi iltimos bayon etilgan murojaat. "
        "Taklif — davlat va jamiyat faoliyatini takomillashtirishga doir tavsiyalarni "
        "o‘z ichiga olgan murojaat. "
        "Shikoyat — buzilgan huquqlarni, erkinliklarni tiklash va qonuniy manfaatlarni "
        "himoya qilish to‘g‘risidagi talab bayon etilgan murojaat. "
        "Elektron murojaat — AKT vositasida, shu jumladan rasmiy veb-saytga joylashtirilgan "
        "murojaat. Takroriy murojaat — avvalgi murojaat bo‘yicha qarordan shikoyat qilinayotgan "
        "yoki norozilik bildirilayotgan murojaat. Anonim murojaat — FISH yoki yashash joyi "
        "ko‘rsatilmagan, yolg‘on ma’lumot berilgan yoxud imzo bilan tasdiqlanmagan murojaat.",
   tags=["ariza", "taklif", "shikoyat", "anonim", "takroriy", "elektron murojaat"]),

 dict(art="6-modda", title="Murojaatlarga qo‘yiladigan talablar",
   text="Jismoniy shaxsning murojaatida FISH va yashash joyi; yuridik shaxsning murojaatida "
        "to‘liq nomi va pochta manzili ko‘rsatilgan bo‘lishi kerak. Murojaatda davlat organining "
        "aniq nomi, mansabdor shaxsning lavozimi va (yoki) FISHi ko‘rsatilib, murojaatning "
        "mohiyati bayon etiladi. Yozma murojaat imzo bilan tasdiqlanadi. Murojaatlar davlat "
        "tilida va boshqa tillarda berilishi mumkin.",
   tags=["talablar", "imzo", "til"]),

 dict(art="23-modda", title="Murojaatlar bo‘yicha ish yuritish",
   text="Kelib tushgan murojaat o‘sha kunning o‘zida, ish vaqti tugagach kelib tushgan bo‘lsa — "
        "keyingi ish kuni ro‘yxatdan o‘tkazilishi kerak. Murojaatni ro‘yxatdan o‘tkazishni "
        "rad etishga yo‘l qo‘yilmaydi.",
   tags=["royxatga olish", "muddat"]),

 dict(art="25-modda", title="Ayrim murojaatlarni ko‘rib chiqish tartibi",
   text="Vakolatiga kirmaydigan murojaatlar besh kunlik muddatdan kechiktirmay tegishli "
        "organlarga yuboriladi va bu haqda murojaat etuvchiga xabar qilinadi. Murojaatlarni "
        "qarorlari ustidan shikoyat qilinayotgan organlarga yuborish taqiqlanadi. "
        "Yuborish uchun zarur ma’lumotlar bo‘lmasa, murojaat besh kun ichida asoslantirilgan "
        "tushuntirish bilan qaytariladi.",
   tags=["tegishlilik", "5 kun", "qayta yuborish"]),

 dict(art="27-modda", title="Murojaatlarga javoblar",
   text="Kо‘rib chiqish natijasi bo‘yicha qaror qabul qilinadi va bu haqda murojaat qiluvchiga "
        "darhol yozma yoki elektron shaklda xabar qilinadi. Javobni rahbar yoki mansabdor shaxs "
        "imzolaydi. Jamoaviy murojaatlarga javob ro‘yxatda birinchi ko‘rsatilgan shaxsga "
        "yuboriladi. Javoblar imkon qadar murojaat etilgan tilda bayon qilinadi va har bir "
        "masala bo‘yicha vajlarni inkor etuvchi yoki tasdiqlovchi aniq asoslarni "
        "(qonunchilik normalariga havolalar bilan) o‘z ichiga olishi kerak.",
   tags=["javob", "til", "asoslash", "havola"]),

 dict(art="28-modda", title="Murojaatlarni ko‘rib chiqish muddatlari",
   text="Ariza yoki shikoyat kelib tushgan kundan e’tiboran 15 kun ichida; qo‘shimcha "
        "o‘rganish va (yoki) tekshirish, qo‘shimcha hujjatlar so‘rab olish talab etilganda — "
        "bir oygacha muddatda ko‘rib chiqiladi. Zarur hollarda muddat rahbar tomonidan "
        "istisno tariqasida uzog‘i bilan bir oyga uzaytirilishi mumkin, bu haqda murojaat "
        "etuvchiga xabar qilinadi. Taklif bir oygacha muddatda ko‘rib chiqiladi; qo‘shimcha "
        "o‘rganishni talab etadigan takliflar haqida 10 kunlik muddatda yozma xabar beriladi.",
   tags=["15 kun", "1 oy", "muddat", "uzaytirish", "муддат", "срок рассмотрения обращения", "сколько дней рассматривается обращение"]),

 dict(art="29-modda", title="Murojaatlarni ko‘rmay qoldirish",
   text="Ko‘rib chiqilmaydi: anonim murojaatlar; vakil orqali berilgan, vakolatni tasdiqlovchi "
        "hujjatsiz murojaatlar; Qonunda belgilangan boshqa talablarga muvofiq bo‘lmagan "
        "murojaatlar. Ko‘rmay qoldirilganda tegishli xulosa tuziladi va rahbar tomonidan "
        "tasdiqlanadi.",
   tags=["anonim", "kormay qoldirish", "аноним мурожаат", "анонимное обращение"]),

 dict(art="30-modda", title="Murojaatlarni ko‘rib chiqishni tugatish",
   text="Tugatiladi: takroriy murojaatda yangi vajlar yoki yangi ochilgan holatlar bo‘lmasa; "
        "murojaat chaqirib olingan yoki tugatish so‘ralgan bo‘lsa; rekvizitlar o‘zgargani "
        "sababli chaqirish imkoni bo‘lmasa; chaqirilgan murojaat qiluvchi kelmasa; "
        "murojaat qiluvchi vafot etib, huquqiy vorislik bo‘lmasa. Takroriy murojaat "
        "asossiz deb topilsa, yozishmalar tugatilishi haqida yozma xabar beriladi.",
   tags=["takroriy", "tugatish"]),

 dict(art="31-modda", title="Javobni tushuntirish va tuzatish",
   text="Murojaat qiluvchining iltimosiga ko‘ra javob mazmunini o‘zgartirmasdan tushuntiriladi, "
        "yo‘l qo‘yilgan xato va arifmetik xatolar tuzatiladi. Bunday iltimos kelib tushgan "
        "kundan 10 kun ichida ko‘rib chiqiladi.",
   tags=["tushuntirish", "tuzatish", "10 kun"]),

 dict(art="19-modda", title="Maxfiylik kafolatlari",
   text="Murojaatlarni ko‘rib chiqishda jismoniy shaxslarning shaxsiy hayoti va yuridik "
        "shaxslarning faoliyati to‘g‘risidagi ma’lumotlar ularning roziligisiz oshkor "
        "etilishiga yo‘l qo‘yilmaydi. Murojaatga taalluqli bo‘lmagan ma’lumotlarni "
        "aniqlashga yo‘l qo‘yilmaydi. Jismoniy shaxsning iltimosiga ko‘ra uning shaxsiga "
        "doir ma’lumot oshkor etilmasligi kerak.",
   tags=["maxfiylik", "shaxsiy malumot", "PII"]),

 dict(art="32-modda", title="Murojaat qiluvchining huquqlari",
   text="Murojaatni ko‘rib chiqish borishi haqida axborot olish; vajlarni shaxsan bayon etish; "
        "tekshiruv materiallari bilan tanishish; qo‘shimcha materiallar taqdim etish; advokat "
        "yordamidan foydalanish; ko‘rib chiqishni tugatishni yoki javobni tushuntirishni "
        "so‘rash; murojaatni chaqirib olish; rad etish ustidan yuqori organga yoki sudga "
        "shikoyat qilish.",
   tags=["huquqlar", "sud"]),
]

# UZIMEI/MNP sohasi bo'yicha asosiy normativ hujjatlar ro'yxati (authority=2)
REGULATIONS = [
 dict(ref="VMQ 778-son, 17.09.2019",
   title="Mobil qurilmalarning xalqaro o‘ziga xos identifikatsiya kodlarini (IMEI) "
         "ro‘yxatga olish tartibi to‘g‘risidagi nizom",
   text="Jismoniy va yuridik shaxslar tomonidan IMEI-kodlarni ro‘yxatga olishning "
        "belgilangan tartibi. 3-bob 7-band: klonlangan va aniqlanmagan IMEI-kodli qurilmalar "
        "Tizimda ro‘yxatga olinmaydi. 6-bob 39-band: klonlangan IMEI aniqlanganda tizim "
        "avtomatik tahlil qilib qurilmani «qora ro‘yxat»ga kiritadi. 61-band: chakana savdo "
        "subyektlari qurilmani olib kirish sanasidan qat’i nazar ro‘yxatdan o‘tkazish uchun "
        "javobgar."),
 dict(ref="VMQ 463-son",
   title="Mobil qurilmalarni olib kirish va ro‘yxatga olish me’yorlari",
   text="Bojsiz olib kirish me’yorlari; IMEI-kod SIM-karta almashtirilishidan qat’i nazar "
        "bir marta ro‘yxatga olinadi; yarim yilda bitta qurilma (planshetlardan tashqari)."),
 dict(ref="VMQ 828-son, 31.12.2020, 61-band",
   title="Chakana savdo subyektlarining javobgarligi",
   text="O‘zbekiston hududida mobil qurilmalar chakana savdosi bilan shug‘ullanuvchi "
        "tadbirkorlik subyektlari qurilmalarni respublika hududiga olib kirish sanasidan "
        "qat’i nazar ularni ro‘yxatdan o‘tkazish uchun javobgar."),
 dict(ref="O‘zR DBQ 526-son nizom",
   title="Bojxona rasmiylashtiruvi tartibi",
   text="Jismoniy shaxslar tomonidan davlat chegarasini kesib o‘tishda olib kiriladigan "
        "mobil qurilmalar bo‘yicha bojxona rasmiylashtiruvi va kirim orderi."),
 dict(ref="PQ 3512-son",
   title="UZIMEI tizimini joriy etish to‘g‘risida",
   text="Mobil qurilmalar IMEI-kodlarini ro‘yxatga olish tizimini tashkil etish."),
 dict(ref="1-sonli Nizom",
   title="Avtomatik ro‘yxatga olinadigan qurilmalar ro‘yxati",
   text="DONGLE, WLAN ROUTER, IoT DEVICE, VEHICLE, E-BOOK, MODULE, CONNECTED COMPUTER, "
        "MODEM, WEARABLES turidagi qurilmalar ilk tarmoq hodisasidan so‘ng avtomatik "
        "ro‘yxatga olinadi."),
]
