"""Honest handling of live-status requests, per the knowledge base's capability rule.

The assistant has no integration with UZIMEI, MNP, customs, operators or any other
external system, so it can never FIND a status. It can EXPLAIN a status the customer
reports, analyse the problem, recommend the next step and route to an operator.

Three deterministic pieces enforce that:

- :func:`detect_status_request` recognises a request to look something up in a live
  system ("IMEI ro'yxatdan o'tganmi?", "blacklistdami?", "raqamim o'tdimi?", "find my
  phone by IMEI") - but not a how-to question ("qanday tekshiraman?"), which the
  knowledge base answers;
- :func:`status_request_reply` says plainly that it cannot check, then keeps helping:
  the official way to check (UZIMEI site, SMS to 1170 or *1170# for an IMEI; the new
  operator's SMS for MNP), what to send back, what happens next - never a dead end;
- :func:`reported_status_reply` explains an official status code the customer pasted
  (GSMA_INVALID, CLONED, UNKNOWN, BLACKLISTED) from the knowledge-base article that owns it;
- :func:`claims_live_check` rejects model-written text that claims a lookup it could
  not have made ("tekshirdim", "tizimdan qaradim", "I checked..."), so a composed
  answer falls back to its approved text instead.

Matching runs on the shared normalised form (Cyrillic transliterated to Latin,
apostrophes dropped), so markers are written in that form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.fact_extraction import _normalize

IMEI_STATUS = "imei_status"
BLACKLIST = "blacklist"
MNP_STATUS = "mnp_status"
MY_DEVICES = "my_devices"
CUSTOMS = "customs"
APPLICATION = "application"
LOCATION = "location"
PAYMENT = "payment"

# The knowledge-base article that governs each kind of lookup request.
SEED_ENTRY_BY_KIND = {
    IMEI_STATUS: "KB-IMEI-STATUS-001",
    BLACKLIST: "KB-LOST-002",
    MNP_STATUS: "KB-MNP-008",
    MY_DEVICES: "KB-IDENTITY-001",
    CUSTOMS: "KB-IMPORT-002",
    APPLICATION: "KB-IMEI-001",
    LOCATION: "KB-IMEI-LOST-001",
    PAYMENT: "KB-IMEI-PAYMENT-001",
}

# A request for the assistant itself to look something up.
_LOOKUP_VERBS = (
    "tekshirib ber",
    "tekshiring",
    "tekshirsangiz",
    "tekshira olasiz",
    "tekshirib kor",
    "bilib ber",
    "qarab ber",
    "korib ber",
    "aniqlab ber",
    "proverte",
    "prover ",
    "mozhete proverit",
    "uznayte",
    "posmotrite",
    "can you check",
    "check my",
    "check if",
    "check whether",
    "check the status",
    "look up",
)
# A how-to question ("how / where do I check?") is answered from the knowledge base.
_HOW_TO = (
    "qanday tekshir",
    "qayerdan tekshir",
    "qaerdan tekshir",
    "qanday bilsa",
    "qanday bilaman",
    "qayerdan bilsa",
    "qayerdan bilaman",
    "kak proverit",
    "kak uznat",
    "gde proverit",
    "how do i check",
    "how can i check",
    "how to check",
    "where can i check",
    "where do i check",
)

# (kind, subject markers, question forms that are a lookup on their own). A kind
# matches on one of its own question forms, or on a subject marker plus a lookup verb.
# Order matters: the more specific kinds are tried first.
_KINDS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        LOCATION,
        ("qayerda", "joylashuv", "lokatsiya", "location", "gde telefon", "mestopolozhen"),
        (
            "qayerdaligini",
            "qayerda ekanini",
            "imei orqali top",
            "imei bilan top",
            "topib bera olasiz",
            "topib bering",
            "qaysi raqamda ishla",
            "find my phone",
            "where is my phone",
            "najti telefon",
            "gde moy telefon",
        ),
    ),
    (
        MY_DEVICES,
        ("nomimga", "nomimda", "pasportimga", "na moe imya", "in my name"),
        (
            "nomimga qaysi",
            "nomimda qaysi",
            "nomimga nima",
            "nomimda nima",
            "pasportimga qaysi",
            "pasportimga royxatdan otgan",
            "kakie ustroystva na moe imya",
            "which devices are registered",
            "which phones are registered",
        ),
    ),
    (
        CUSTOMS,
        ("bojxona", "tamozhn", "customs"),
        (
            "bojxonada telefonim korinadimi",
            "bojxonada korinadimi",
            "bojxona bazasida bormi",
            "vidno na tamozhne",
        ),
    ),
    (
        APPLICATION,
        ("arizam", "murojaatim", "zayavk", "my application"),
        (
            "arizam qayergacha",
            "arizam qaerga",
            "arizam qayerda",
            "arizam nima boldi",
            "murojaatim qayerda",
            "status zayavki",
            "gde moya zayavka",
        ),
    ),
    (
        PAYMENT,
        ("tolov", "oplat", "platezh", "payment"),
        (
            "tolovim otdimi",
            "tolovim otganmi",
            "tolov otdimi",
            "tolov otganmi",
            "tolovim tushdimi",
            "tolov tushdimi",
            "oplata proshla",
            "platezh proshel",
            "did my payment go through",
            "has my payment gone through",
            "is my payment in the system",
        ),
    ),
    (
        BLACKLIST,
        ("blacklist", "qora royxat", "chernom spisk", "cherniy spisok"),
        (
            "blacklistdami",
            "blacklistda emasmi",
            "blacklistdan chiqqanmi",
            "blacklistda qolganmi",
            "qora royxatdami",
            "qora royxatda emasmi",
            "qora royxatda qolganmi",
            "qora royxatdan chiqqanmi",
            "is my phone blacklisted",
        ),
    ),
    (
        MNP_STATUS,
        ("mnp", "operatorga", "kochir", "perenos", "ported"),
        (
            "operatorga otdimi",
            "operatorga otganmi",
            "raqamim otdimi",
            "raqamim otganmi",
            "otkazgandim otdimi",
            "nomer pereshel",
            "perenesli li",
            "has my number been ported",
            "was my number ported",
        ),
    ),
    (
        IMEI_STATUS,
        ("imei", "telefonim", "status"),
        (
            "royxatdan otganmi",
            "royxatdan otdimi",
            "registratsiya qilinganmi",
            "registratsiyadan otganmi",
            "zaregistrirovan li",
            "is my imei registered",
            "is my phone registered",
        ),
    ),
)


def _has(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def detect_status_request(message: str) -> str | None:
    """The kind of live-system lookup the message asks for, or None.

    A how-to question ("IMEI statusini qanday tekshiraman?") is not a lookup request:
    it is a request for instructions, which the knowledge base answers.
    """
    text = " " + " ".join(re.sub(r"[^\w]+", " ", _normalize(message)).split()) + " "
    if _has(text, _HOW_TO):
        return None
    wants_lookup = _has(text, _LOOKUP_VERBS)
    for kind, subjects, questions in _KINDS:
        if _has(text, questions) or (wants_lookup and _has(text, subjects)):
            return kind
    return None


# --- replies --------------------------------------------------------------------

_CANNOT_CHECK = {
    "uz": "Buni men tizimdan bevosita tekshira olmayman.",
    "uz_cyrl": "Буни мен тизимдан бевосита текшира олмайман.",
    "ru": "Я не могу проверить это напрямую в системе.",
    "en": "I can't check this directly in the system.",
    "kaa": "Buni men sistemadan tikkeley tekserip bere almayman.",
}

_REPLIES: dict[str, dict[str, str]] = {
    IMEI_STATUS: {
        "uz": "IMEI holatini men tizimdan bevosita tekshira olmayman. Uni UZIMEI sayti, 1170 "
        "raqamiga SMS yoki *1170# orqali tekshirishingiz mumkin. Sizga chiqqan status yoki "
        "xabarni yuborsangiz, nimani anglatishini va keyin nima qilish kerakligini "
        "tushuntirib beraman.",
        "uz_cyrl": "IMEI ҳолатини мен тизимдан бевосита текшира олмайман. Уни UZIMEI сайти, 1170 "
        "рақамига SMS ёки *1170# орқали текширишингиз мумкин. Сизга чиққан статус ёки "
        "хабарни юборсангиз, нимани англатишини ва кейин нима қилиш кераклигини "
        "тушунтириб бераман.",
        "ru": "Я не могу напрямую проверить статус IMEI в системе. Проверить его можно на сайте "
        "UZIMEI, отправив SMS на номер 1170 или через *1170#. Пришлите статус или сообщение, "
        "которое вы получили, — объясню, что оно значит и что делать дальше.",
        "en": "I can't check an IMEI's status directly in the system. You can check it on the "
        "UZIMEI website, by SMS to 1170, or via *1170#. Send me the status or message you get "
        "and I'll explain what it means and what to do next.",
        "kaa": "IMEI jaǵdayın men sistemadan tikkeley tekserip bere almayman. Onı UZIMEI saytı, "
        "1170 nomerine SMS yamasa *1170# arqalı tekseriwińiz múmkin. Sizge shıqqan status "
        "yamasa xabardı jiberseńiz, neni ańlatatuǵının hám keyin ne qılıw kerekligin "
        "túsindirip beremen.",
    },
    BLACKLIST: {
        "uz": "Qora ro'yxat (blacklist) holatini men tizimdan bevosita tekshira olmayman. "
        "Rasmiy tekshiruvda qanday status chiqqanini yuborsangiz, ma'nosini tushuntiraman. "
        "Agar telefon yo'qolib, keyin topilgan bo'lsa va hali qora ro'yxatda ko'rinsa, "
        "yo'qolgan qurilma bo'yicha avvalgi rasmiy jarayon bilan bog'liq tashkilotga "
        "murojaat qilish kerak.",
        "uz_cyrl": "Қора рўйхат (blacklist) ҳолатини мен тизимдан бевосита текшира олмайман. "
        "Расмий текширувда қандай статус чиққанини юборсангиз, маъносини тушунтираман. "
        "Агар телефон йўқолиб, кейин топилган бўлса ва ҳали қора рўйхатда кўринса, "
        "йўқолган қурилма бўйича аввалги расмий жараён билан боғлиқ ташкилотга "
        "мурожаат қилиш керак.",
        "ru": "Я не могу напрямую проверить, находится ли устройство в чёрном списке. "
        "Пришлите статус, который показала официальная проверка, — объясню, что он значит. "
        "Если телефон был утерян, потом найден и всё ещё числится в чёрном списке, нужно "
        "обратиться в организацию, связанную с прежней официальной процедурой по утере.",
        "en": "I can't check the blacklist status directly in the system. Send me the status "
        "the official check shows and I'll explain it. If the phone was lost, then found, "
        "and still shows as blacklisted, contact the organisation involved in the original "
        "official lost-device process.",
        "kaa": "Qara dizim (blacklist) jaǵdayın men sistemadan tikkeley tekserip bere "
        "almayman. Rásmiy tekseriwde qanday status shıqqanın jiberseńiz, mánisin "
        "túsindiremen. Eger telefon joǵalıp, keyin tabılǵan bolsa hám ele qara dizimde "
        "kórinse, joǵalǵan qurılma boyınsha aldınǵı rásmiy processke baylanıslı shólkemge "
        "múráját etiw kerek.",
    },
    MNP_STATUS: {
        "uz": "MNP tizimidagi real statusni bevosita tekshira olmayman. Raqam muvaffaqiyatli "
        "ko'chirilganda yangi operator SMS orqali xabar beradi. Agar sizga SMS yoki rad sababi "
        "kelgan bo'lsa, shu xabarni yuboring — keyingi qadamni aytaman.",
        "uz_cyrl": "MNP тизимидаги реал статусни бевосита текшира олмайман. Рақам муваффақиятли "
        "кўчирилганда янги оператор SMS орқали хабар беради. Агар сизга SMS ёки рад сабаби "
        "келган бўлса, шу хабарни юборинг — кейинги қадамни айтаман.",
        "ru": "Я не могу напрямую проверить статус переноса номера в системе MNP. Когда перенос "
        "успешно завершён, новый оператор сообщает об этом по SMS. Если вам пришло SMS или "
        "причина отказа, пришлите это сообщение — подскажу следующий шаг.",
        "en": "I can't check the real porting status in the MNP system. When the number has "
        "been ported successfully, the new operator lets you know by SMS. If you received an "
        "SMS or a rejection reason, send it to me and I'll tell you the next step.",
        "kaa": "MNP sistemasındaǵı real statustı tikkeley tekserip bere almayman. Nomer tabıslı "
        "kóshirilgende jańa operator SMS arqalı xabar beredi. Eger sizge SMS yamasa biykar "
        "etiw sebebi kelgen bolsa, sol xabardı jiberiń — keyingi qádemdi aytaman.",
    },
    MY_DEVICES: {
        "uz": "Men sizning nomingizga ro'yxatdan o'tgan qurilmalarni tizimdan bevosita ko'ra "
        "olmayman. Buni tegishli rasmiy xizmat orqali tekshirishingiz kerak. Agar u yerda "
        "sizga notanish qurilma chiqsa, natijani menga yuboring — keyingi qadamni "
        "tushuntirib beraman.",
        "uz_cyrl": "Мен сизнинг номингизга рўйхатдан ўтган қурилмаларни тизимдан бевосита "
        "кўра олмайман. Буни тегишли расмий хизмат орқали текширишингиз керак. Агар у ерда "
        "сизга нотаниш қурилма чиқса, натижани менга юборинг — кейинги қадамни "
        "тушунтириб бераман.",
        "ru": "Я не вижу устройства, зарегистрированные на ваше имя: напрямую в систему у "
        "меня доступа нет. Это проверяется через соответствующий официальный сервис. Если "
        "там окажется незнакомое устройство, пришлите результат — объясню следующий шаг.",
        "en": "I can't see which devices are registered in your name — I have no direct "
        "access to the system. Check this through the relevant official service. If an "
        "unfamiliar device shows up there, send me the result and I'll explain the next step.",
        "kaa": "Men sizdiń atıńızǵa dizimnen ótken qurılmalardı sistemadan tikkeley kóre "
        "almayman. Buni tiyisli rásmiy xızmet arqalı tekseriwińiz kerek. Eger ol jerde "
        "sizge tanıs emes qurılma shıqsa, nátiyjeni maǵan jiberiń — keyingi qádemdi "
        "túsindirip beremen.",
    },
    CUSTOMS: {
        "uz": "Bojxona tizimidagi ma'lumotni bevosita tekshira olmayman. Agar IMEI "
        "registratsiyasida chiqayotgan xabarni yuborsangiz, sababini aniqlashga yordam "
        "beraman.",
        "uz_cyrl": "Божхона тизимидаги маълумотни бевосита текшира олмайман. Агар IMEI "
        "регистрациясида чиқаётган хабарни юборсангиз, сабабини аниқлашга ёрдам бераман.",
        "ru": "Я не могу напрямую проверить данные в таможенной системе. Пришлите сообщение, "
        "которое появляется при регистрации IMEI, — помогу понять причину.",
        "en": "I can't check customs-system data directly. Send me the message you get when "
        "registering the IMEI and I'll help work out the cause.",
        "kaa": "Bajıxana sistemasındaǵı maǵlıwmattı tikkeley tekserip bere almayman. IMEI "
        "dizimge alıwda shıǵıp atırǵan xabardı jiberseńiz, sebebin anıqlawǵa járdem beremen.",
    },
    APPLICATION: {
        "uz": "Arizangiz holatini men tizimdan bevosita tekshira olmayman. Arizani "
        "topshirgan rasmiy xizmatda sizga qanday status yoki xabar ko'rinayotganini "
        "yuborsangiz, nimani anglatishini va keyingi qadamni tushuntirib beraman.",
        "uz_cyrl": "Аризангиз ҳолатини мен тизимдан бевосита текшира олмайман. Аризани "
        "топширган расмий хизматда сизга қандай статус ёки хабар кўринаётганини "
        "юборсангиз, нимани англатишини ва кейинги қадамни тушунтириб бераман.",
        "ru": "Я не могу напрямую проверить статус вашей заявки. Пришлите статус или "
        "сообщение, которое показывает официальный сервис, куда вы её подали, — объясню, "
        "что оно значит и что делать дальше.",
        "en": "I can't check your application's status directly in the system. Send me the "
        "status or message the official service you applied through shows, and I'll explain "
        "what it means and the next step.",
        "kaa": "Arzańızdıń jaǵdayın men sistemadan tikkeley tekserip bere almayman. Arza "
        "tapsırǵan rásmiy xızmette sizge qanday status yamasa xabar kórinip atırǵanın "
        "jiberseńiz, neni ańlatatuǵının hám keyingi qádemdi túsindirip beremen.",
    },
    LOCATION: {
        "uz": "Men IMEI orqali qurilmaning joylashuvini yoki hozir qaysi raqamda ishlayotganini "
        "tekshira olmayman. Yo'qolgan yoki o'g'irlangan telefon bo'yicha IIBga (ichki ishlar "
        "organlariga) ariza bilan murojaat qilish kerak. Arizada ko'rsatish uchun qurilmaning "
        "ishlab chiqaruvchisi, modeli va IMEI'larini tayyorlab qo'ying.",
        "uz_cyrl": "Мен IMEI орқали қурилманинг жойлашувини ёки ҳозир қайси рақамда "
        "ишлаётганини текшира олмайман. Йўқолган ёки ўғирланган телефон бўйича ИИБга (ички "
        "ишлар органларига) ариза билан мурожаат қилиш керак. Аризада кўрсатиш учун "
        "қурилманинг ишлаб чиқарувчиси, модели ва IMEI'ларини тайёрлаб қўйинг.",
        "ru": "Я не могу определить по IMEI, где находится устройство или с каким номером оно "
        "сейчас работает. По утерянному или украденному телефону нужно подать заявление в "
        "органы внутренних дел. Подготовьте для заявления производителя, модель и IMEI "
        "устройства.",
        "en": "I can't use an IMEI to find a device's location or which number it is currently "
        "used with. For a lost or stolen phone, file a report with the internal affairs "
        "bodies (police). Have the device's manufacturer, model and IMEI(s) ready for it.",
        "kaa": "Men IMEI arqalı qurılmanıń jaylasqan ornın yamasa házir qaysı nomerde islep "
        "atırǵanın tekserip bere almayman. Joǵalǵan yamasa urlanǵan telefon boyınsha ishki "
        "isler organlarına arza menen múráját etiw kerek. Arza ushın qurılmanıń islep "
        "shıǵarıwshısın, modelin hám IMEI'lerin tayarlap qoyıń.",
    },
    PAYMENT: {
        "uz": "To'lov tizimidagi ma'lumotni men bevosita tekshira olmayman. To'lov qilgan "
        "ilova yoki bankdagi tranzaksiya holatini ko'ring va sizga chiqqan xabar yoki chekni "
        "yuboring — nimani anglatishini va keyingi qadamni tushuntirib beraman.",
        "uz_cyrl": "Тўлов тизимидаги маълумотни мен бевосита текшира олмайман. Тўлов қилган "
        "илова ёки банкдаги транзакция ҳолатини кўринг ва сизга чиққан хабар ёки чекни "
        "юборинг — нимани англатишини ва кейинги қадамни тушунтириб бераман.",
        "ru": "Я не могу напрямую проверить данные платёжной системы. Посмотрите статус "
        "транзакции в приложении или банке, через который платили, и пришлите сообщение или "
        "чек — объясню, что это значит и что делать дальше.",
        "en": "I can't check the payment system directly. Look at the transaction status in "
        "the app or bank you paid through, and send me the message or receipt you see — I'll "
        "explain what it means and the next step.",
        "kaa": "Tólem sistemasındaǵı maǵlıwmattı men tikkeley tekserip bere almayman. Tólem "
        "qılǵan qosımsha yamasa banktegi tranzakciya jaǵdayın kóriń hám sizge shıqqan xabardı "
        "yamasa chekti jiberiń — neni ańlatatuǵının túsindirip beremen.",
    },
}


def status_request_reply(kind: str, lang: str) -> str:
    """Say plainly that it cannot check, then keep helping (never a dead end)."""
    by_lang = _REPLIES.get(kind)
    if by_lang is None:
        return _CANNOT_CHECK.get(lang, _CANNOT_CHECK["uz"])
    return by_lang.get(lang) or by_lang["uz"]


# --- a status code the customer reports ------------------------------------------

# Official status codes are matched case-sensitively as whole tokens, so an ordinary
# word ("unknown device") never reads as a reported status.
_STATUS_CODE = re.compile(r"(?<![A-Za-z_])(GSMA_INVALID|CLONED|UNKNOWN|BLACKLISTED)(?![A-Za-z_])")

_STATUS_REPLIES: dict[str, dict[str, str]] = {
    "GSMA_INVALID": {
        "uz": "GSMA_INVALID — bu qurilma IMEI kodi GSMA belgilagan talablarga javob "
        "bermasligini bildiradi. Bunday IMEI'ni odatiy tartibda ro'yxatdan o'tkazishning "
        "texnik imkoni yo'q, shuning uchun qayta-qayta urinish natija bermaydi. Agar bu "
        "natija noto'g'ri deb hisoblasangiz, operator yoki mutaxassisga murojaat qiling.",
        "uz_cyrl": "GSMA_INVALID — бу қурилма IMEI коди GSMA белгилаган талабларга жавоб "
        "бермаслигини билдиради. Бундай IMEI'ни одатий тартибда рўйхатдан ўтказишнинг "
        "техник имкони йўқ, шунинг учун қайта-қайта уриниш натижа бермайди. Агар бу "
        "натижа нотўғри деб ҳисобласангиз, оператор ёки мутахассисга мурожаат қилинг.",
        "ru": "GSMA_INVALID означает, что IMEI устройства не соответствует требованиям GSMA. "
        "Такой IMEI технически нельзя зарегистрировать в обычном порядке, поэтому повторные "
        "попытки не помогут. Если вы считаете результат ошибочным, обратитесь к оператору "
        "или специалисту.",
        "en": "GSMA_INVALID means the device's IMEI does not meet the GSMA requirements. "
        "Such an IMEI can't technically be registered the usual way, so retrying won't "
        "help. If you believe the result is wrong, contact an operator or a specialist.",
        "kaa": "GSMA_INVALID — bul qurılmanıń IMEI kodı GSMA belgilegen talaplarǵa juwap "
        "bermeytuǵının bildiredi. Bunday IMEI'di ádettegi tártipte dizimge alıwdıń texnikalıq "
        "imkanı joq, sonlıqtan qayta-qayta urınıw nátiyje bermeydi. Eger bul nátiyje qáte "
        "dep esaplasańız, operator yamasa qánigege múráját etiń.",
    },
    "CLONED": {
        "uz": "CLONED — rasmiy tizim bu IMEI'ni klonlangan (boshqa qurilmada ham uchraydigan) "
        "deb belgilaganini bildiradi. Bunday holatda oddiy registratsiyani qayta-qayta "
        "takrorlash yordam bermaydi. Qurilmangiz qanday turdagi qurilma — telefonmi yoki "
        "modem, tracker kabi IoT qurilmami? Modelini yozing; zarur bo'lsa operator yoki "
        "mutaxassisga yo'naltiraman.",
        "uz_cyrl": "CLONED — расмий тизим бу IMEI'ни клонланган (бошқа қурилмада ҳам "
        "учрайдиган) деб белгилаганини билдиради. Бундай ҳолатда оддий регистрацияни "
        "қайта-қайта такрорлаш ёрдам бермайди. Қурилмангиз қандай турдаги қурилма — "
        "телефонми ёки модем, трекер каби IoT қурилмами? Моделини ёзинг; зарур бўлса "
        "оператор ёки мутахассисга йўналтираман.",
        "ru": "CLONED означает, что официальная система отметила этот IMEI как клонированный "
        "(встречающийся и на другом устройстве). Повторять обычную регистрацию в этом "
        "случае бесполезно. Что это за устройство — телефон или IoT-устройство вроде модема "
        "или трекера? Напишите модель; при необходимости направлю к оператору или "
        "специалисту.",
        "en": "CLONED means the official system has flagged this IMEI as cloned (also seen "
        "on another device). Repeating the normal registration won't help. What kind of "
        "device is it — a phone, or an IoT device such as a modem or tracker? Tell me the "
        "model; if needed I'll route you to an operator or specialist.",
        "kaa": "CLONED — rásmiy sistema bul IMEI'di klonlanǵan (basqa qurılmada da "
        "ushırasatuǵın) dep belgilegenin bildiredi. Bunday jaǵdayda ádettegi dizimge alıwdı "
        "qayta-qayta tákirarlaw járdem bermeydi. Qurılmańız qanday túrdegi qurılma — "
        "telefonba yamasa modem, treker sıyaqlı IoT qurılmasıma? Modelin jazıń.",
    },
    "UNKNOWN": {
        "uz": "UNKNOWN — rasmiy tizim bu IMEI'ga mos qurilmani aniqlay olmaganini bildiradi. "
        "Sababini aniqlash uchun qurilma modeli va turini (telefon, modem, tracker va h.k.) "
        "hamda tizimda chiqqan to'liq xabarni yozing; zarur bo'lsa operator yoki "
        "mutaxassisga yo'naltiraman.",
        "uz_cyrl": "UNKNOWN — расмий тизим бу IMEI'га мос қурилмани аниқлай олмаганини "
        "билдиради. Сабабини аниқлаш учун қурилма модели ва турини (телефон, модем, трекер "
        "ва ҳ.к.) ҳамда тизимда чиққан тўлиқ хабарни ёзинг; зарур бўлса оператор ёки "
        "мутахассисга йўналтираман.",
        "ru": "UNKNOWN означает, что официальная система не смогла определить устройство по "
        "этому IMEI. Чтобы понять причину, напишите модель и тип устройства (телефон, модем, "
        "трекер и т. п.) и полный текст сообщения; при необходимости направлю к оператору "
        "или специалисту.",
        "en": "UNKNOWN means the official system could not identify a device for this IMEI. "
        "To find the cause, tell me the device model and type (phone, modem, tracker, etc.) "
        "and the full message shown; if needed I'll route you to an operator or specialist.",
        "kaa": "UNKNOWN — rásmiy sistema bul IMEI'ge sáykes qurılmanı anıqlay almaǵanın "
        "bildiredi. Sebebin anıqlaw ushın qurılma modeli hám túrin hám de sistemada "
        "shıqqan tolıq xabardı jazıń.",
    },
    "BLACKLISTED": {
        "uz": "BLACKLISTED — qurilma qora ro'yxatda ekanini bildiradi. Bunday qurilmani "
        "oddiy registratsiya bilan ishlatib bo'lmaydi. Agar telefon yo'qolib, keyin topilgan "
        "bo'lsa, yo'qolgan qurilma bo'yicha avvalgi rasmiy jarayon bilan bog'liq tashkilotga "
        "murojaat qiling. Boshqa holatda operator yoki mutaxassisga yo'naltiraman.",
        "uz_cyrl": "BLACKLISTED — қурилма қора рўйхатда эканини билдиради. Бундай қурилмани "
        "оддий регистрация билан ишлатиб бўлмайди. Агар телефон йўқолиб, кейин топилган "
        "бўлса, йўқолган қурилма бўйича аввалги расмий жараён билан боғлиқ ташкилотга "
        "мурожаат қилинг. Бошқа ҳолатда оператор ёки мутахассисга йўналтираман.",
        "ru": "BLACKLISTED означает, что устройство находится в чёрном списке, и обычная "
        "регистрация здесь не поможет. Если телефон был утерян и потом найден, обратитесь в "
        "организацию, связанную с прежней официальной процедурой по утере. В остальных "
        "случаях направлю к оператору или специалисту.",
        "en": "BLACKLISTED means the device is on the blacklist, so normal registration "
        "won't help. If the phone was lost and later found, contact the organisation "
        "involved in the original official lost-device process. Otherwise I'll route you "
        "to an operator or specialist.",
        "kaa": "BLACKLISTED — qurılma qara dizimde ekenin bildiredi. Bunday qurılmanı "
        "ádettegi dizimge alıw menen isletip bolmaydı. Eger telefon joǵalıp, keyin tabılǵan "
        "bolsa, joǵalǵan qurılma boyınsha aldınǵı rásmiy processke baylanıslı shólkemge "
        "múráját etiń.",
    },
}


@dataclass(frozen=True)
class ReportedStatus:
    code: str
    seed_entry_id: str
    reply: str


_SEED_ENTRY_BY_CODE = {
    "GSMA_INVALID": "KB-IMEI-001",
    "CLONED": "KB-IMEI-002",
    "UNKNOWN": "KB-IMEI-002",
    "BLACKLISTED": "KB-IMEI-002",
}


def reported_status_reply(message: str, lang: str) -> ReportedStatus | None:
    """Explain an official status code the customer pasted, or None if there is none."""
    found = _STATUS_CODE.search(message)
    if found is None:
        return None
    code = found.group(1)
    by_lang = _STATUS_REPLIES[code]
    return ReportedStatus(
        code=code,
        seed_entry_id=_SEED_ENTRY_BY_CODE[code],
        reply=by_lang.get(lang) or by_lang["uz"],
    )


# --- output guard -----------------------------------------------------------------

# Phrases claiming a live lookup the assistant cannot make (normalised form).
_LIVE_CHECK_CLAIMS = (
    "tekshirib koraman",
    "tekshirib chiqaman",
    "tizimdan qarayman",
    "tizimdan qaradim",
    "tizimdan tekshirdim",
    "imeiingizni tekshirdim",
    "tekshirdim",
    "sizning status hozir",
    "sizning statusingiz hozir",
    "topib beraman",
    "ya proveril",
    "ya proverila",
    "ya proveryu",
    "seychas proveryu",
    "posmotrel v sisteme",
    "posmotrela v sisteme",
    "i checked",
    "i have checked",
    "ive checked",
    "let me check",
    "i will check",
    "ill check",
    "i looked up",
    "your current status is",
    "tolovingiz tizimda",
    "tolov tizimda mavjud",
    "arizangizni tekshirdim",
    "your payment is in the system",
    "your payment has been confirmed in the system",
    "vash platezh est v sisteme",
)


def claims_live_check(text: str) -> bool:
    """True when composed text claims it looked something up in a live system."""
    norm = _normalize(text)
    return any(claim in norm for claim in _LIVE_CHECK_CLAIMS)
