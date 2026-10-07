"""Intent control: answer what the customer is asking NOW, not what they asked before.

Every turn starts from one question - what is the customer's current goal? The intent
of an earlier message is never carried into a new one: when a fresh, explicit request
changes the goal (a fee complaint becomes "I paid, now I need the receipt"), the old
diagnostic flow is dropped and the new goal is answered directly.

This module holds the deterministic pieces of that control:

- :func:`detect_intent` - the explicit goal stated in this message, if any (an
  explicit request outranks anything inferred from earlier turns or the KB);
- :func:`transaction_facts` - completed actions the customer reports (registration
  succeeded, payment made, receipt missing), so a successful step is respected and
  never diagnosed as a failure;
- the replies for those goals, in every supported language. They follow the house
  rules: get to the point in the first sentence, do not retell the customer's story,
  never claim access to a system the assistant does not have, never invent a
  procedure the knowledge base does not contain, and ask at most one question - only
  when its answer changes the next step.

Matching runs on the shared normalised form (Cyrillic transliterated to Latin,
apostrophes dropped, punctuation removed).
"""

from __future__ import annotations

import re

from app.domain.case_state import Fact, FactStatus
from app.services.fact_extraction import _normalize

PAYMENT_RECEIPT = "payment_receipt_request"
REGISTRATION_FEE = "registration_fee_question"
WRONG_PORT = "mnp_wrong_port"
ROAMING_DEBT_AFTER_PORT = "mnp_roaming_debt_after_port"

# The one question a fee complaint needs: where the phone came from decides which
# registration category (and so which charge) applies.
FEE_ORIGIN_QUESTION = "intent:registration_fee:device_origin"


def _text(message: str) -> str:
    return " " + " ".join(re.sub(r"[^\w]+", " ", _normalize(message)).split()) + " "


def _has(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


# --- payment receipt -------------------------------------------------------------

_RECEIPT = re.compile(r" (chek|cheki|chekni|chekim|chekini|cheka|cheku|kvitan\w*|receipt\w*) ")
# A payment receipt, not a shop/purchase receipt ("xarid cheki") or a box label.
_PAYMENT_CONTEXT = (
    "tolov",
    "toladim",
    "tolagan",
    "paid",
    "pay ",
    "payment",
    "oplat",
    "platezh",
    "elektron",
    "electronic",
    "official",
    "rasmiy",
    "reimburs",
    "accounting",
    "buxgalter",
    "buhgalter",
    "registrats",
    "registration",
    "uzimei",
)
_PURCHASE_CONTEXT = ("xarid", "pokupk", "purchase", "dokon", "magazin", "quti", "korobk")


def _is_receipt_request(text: str) -> bool:
    if not _RECEIPT.search(text):
        return False
    return _has(text, _PAYMENT_CONTEXT) and not _has(text, _PURCHASE_CONTEXT)


# --- registration fee complaint -----------------------------------------------------

_FEE_COMPLAINT = (
    "qimmat",
    "dorogo",
    "dorogaya",
    "dorogoy",
    "slishkom mnogo",
    "pochemu takaya summa",
    "vysokaya summa",
    "expensive",
    "too much",
    "overcharg",
    "nega bunday summa",
    "nega bunaqa summa",
    "summa juda katta",
    "juda kop pul",
)
_AMOUNT = re.compile(r"\d[\d\s.,]*\d\s*(som|sum|uzs|soum)\b|\buzs\s*\d", re.IGNORECASE)


# A number ported without the customer's request: high-risk (possibly unauthorised),
# never treated as an ordinary MNP question. A definition question ("Xato ko'chirish
# nima?") is left to the knowledge base.
_WRONG_PORT = (
    "soramasdan kochir",
    "soramay kochir",
    "aytmasdan kochir",
    "bilmasdan kochir",
    "ruxsatsiz kochir",
    "roziligimsiz kochir",
    "xato kochirib",
    "xato kochirildi",
    "xato kochirilgan",
    "notogri raqam kochib",
    "notogri raqamni kochir",
    "po oshibke perenes",
    "perenesli po oshibke",
    "bez moego soglasiya perenes",
    "perenesli bez",
    "ported without my",
    "wrong number ported",
    "number was ported by mistake",
    "ported by mistake",
)
# "...men so'ramasdan boshqa operatorga ko'chirishdi": the two signals may be apart.
_WITHOUT_CONSENT = (
    "soramasdan",
    "soramay",
    "aytmasdan",
    "bilmasdan",
    "ruxsatsiz",
    "roziligimsiz",
    "arizasiz",
    "talabnomasiz",
)
_PORT_WORDS = ("mnp", "kochir", "kochgan", "kochdi", "perenos", "perenes", "port")
_DEBT_WORDS = ("qarz", "dolg", "debt")


def detect_intent(message: str) -> str | None:
    """The goal this message explicitly states, or None.

    A payment-receipt request wins over a fee complaint: "it was expensive, but now I
    only need the receipt" is a receipt request.
    """
    text = _text(message)
    wrong_port = _has(text, _WRONG_PORT) or (
        _has(text, _WITHOUT_CONSENT) and " kochir" in text.replace("kochib", "kochir")
    )
    if wrong_port and " nima " not in text:
        return WRONG_PORT
    if (
        ("rouming" in text or "roaming" in text)
        and _has(text, _PORT_WORDS)
        and _has(text, _DEBT_WORDS)
    ):
        return ROAMING_DEBT_AFTER_PORT
    if _is_receipt_request(text):
        return PAYMENT_RECEIPT
    if _has(text, _FEE_COMPLAINT):
        return REGISTRATION_FEE
    return None


def mentions_amount(message: str) -> bool:
    """True when the message quotes a charged amount (e.g. "2 620 786,6 so'm")."""
    return _AMOUNT.search(_normalize(message)) is not None


# --- completed actions the customer reports ------------------------------------------

_REGISTRATION_SUCCESS = (
    "registratsiya muvaffaqiyatli",
    "muvaffaqiyatli royxatdan",
    "royxatdan muvaffaqiyatli",
    "muvaffaqiyatli otdi",
    "registratsiya boldi",
    "registration was successful",
    "registration was completed",
    "registration successful",
    "successfully registered",
    "registered successfully",
    "registration completed",
    "i registered",
    "uspeshno zaregistr",
    "registratsiya proshla",
)
_PAYMENT_SUCCESS = (
    "tolov qildim",
    "tolovni qildim",
    "tolovni amalga oshirdim",
    "tolov qilindi",
    "toladim",
    " paid ",
    "i paid",
    "payment was successful",
    "oplatil",
    "zaplatil",
    "oplata proshla",
)


def transaction_facts(message: str, *, turn_id: int) -> list[Fact]:
    """Completed steps the customer states: success is respected, never re-diagnosed."""
    text = _text(message)
    found: list[tuple[str, str]] = []
    if _has(text, _REGISTRATION_SUCCESS):
        found.append(("registration_status", "success"))
    if _has(text, _PAYMENT_SUCCESS):
        found.append(("payment_status", "success"))
    if _is_receipt_request(text):
        found.append(("receipt_status", "missing"))
    return [
        Fact(name=name, value=value, status=FactStatus.EXPLICIT, source="user", turn_id=turn_id)
        for name, value in found
    ]


# --- replies -------------------------------------------------------------------------

# First sentence: the essence of the problem, without retelling the customer's story.
_RECEIPT_LEAD_SUCCESS = {
    "uz": "Tushundim. Bu registratsiya muammosi emas — sizga to'lovning rasmiy elektron "
    "tasdig'i kerak.",
    "uz_cyrl": "Тушундим. Бу регистрация муаммоси эмас — сизга тўловнинг расмий электрон "
    "тасдиғи керак.",
    "ru": "Понял. Это не проблема регистрации — вам нужно официальное электронное "
    "подтверждение платежа.",
    "en": "Understood. This isn't a registration problem — what you need is official "
    "electronic confirmation of the payment.",
    "kaa": "Túsindim. Bul dizimge alıw máselesi emes — sizge tólemniń rásmiy elektron "
    "tastıyıǵı kerek.",
}
_RECEIPT_LEAD = {
    "uz": "Tushundim, sizga to'lovning rasmiy elektron tasdig'i (chek) kerak.",
    "uz_cyrl": "Тушундим, сизга тўловнинг расмий электрон тасдиғи (чек) керак.",
    "ru": "Понял, вам нужно официальное электронное подтверждение платежа (чек).",
    "en": "Understood — you need official electronic confirmation of the payment (a receipt).",
    "kaa": "Túsindim, sizge tólemniń rásmiy elektron tastıyıǵı (chek) kerek.",
}
_RECEIPT_BODY = {
    "uz": "Men UZIMEI to'lov tizimiga kira olmayman va chekni o'zim chiqarib bera olmayman. "
    "Bilim bazasida elektron chekni qayta olish tartibi ko'rsatilmagan, shuning uchun "
    "rasmiy tasdiqni to'lovni qabul qilgan tashkilot yoki to'lov kanalidan so'rash kerak. "
    "Murojaat qilganda ariza raqami, to'lov summasi, sanasi va karta tranzaksiyasi "
    "tasdig'ini tayyorlab qo'ying. Bank yoki to'lov ilovasidagi tranzaksiya chekini ham "
    "saqlang — u to'lovni aniqlashga yordam beradi.",
    "uz_cyrl": "Мен UZIMEI тўлов тизимига кира олмайман ва чекни ўзим чиқариб бера олмайман. "
    "Билим базасида электрон чекни қайта олиш тартиби кўрсатилмаган, шунинг учун расмий "
    "тасдиқни тўловни қабул қилган ташкилот ёки тўлов каналидан сўраш керак. Мурожаат "
    "қилганда ариза рақами, тўлов суммаси, санаси ва карта транзакцияси тасдиғини "
    "тайёрлаб қўйинг. Банк ёки тўлов иловасидаги транзакция чекини ҳам сақланг — у "
    "тўловни аниқлашга ёрдам беради.",
    "ru": "У меня нет доступа к платёжной системе UZIMEI, и выдать чек сам я не могу. В базе "
    "знаний не описан порядок повторного получения электронного чека, поэтому официальное "
    "подтверждение нужно запросить у организации или платёжного канала, через который "
    "проходил платёж. Подготовьте номер заявки, сумму и дату платежа и подтверждение "
    "транзакции по карте. Сохраните и чек транзакции из банка или платёжного приложения — "
    "он поможет найти платёж.",
    "en": "I can't access the UZIMEI payment system or issue the receipt myself. The "
    "information I have doesn't describe a self-service way to get a duplicate e-receipt, "
    "so official confirmation should be requested from the organisation or payment channel "
    "that processed the payment. Have the application number, payment amount, payment date "
    "and the card transaction confirmation ready when you contact them. If you already have "
    "a bank or payment-app transaction receipt, keep it too — it helps identify the payment "
    "while the official confirmation is being requested.",
    "kaa": "Men UZIMEI tólem sistemasına kire almayman hám chekti ózim shıǵarıp bere "
    "almayman. Bilim bazasında elektron chekti qayta alıw tártibi kórsetilmegen, sonlıqtan "
    "rásmiy tastıyıqtı tólemdi qabıl etken shólkemnen yamasa tólem kanalınan soraw kerek. "
    "Múráját etkende arza nomerin, tólem summasın, sánesin hám karta tranzakciyası "
    "tastıyıǵın tayarlap qoyıń. Bank yamasa tólem qosımshasındaǵı tranzakciya chekin de "
    "saqlań — ol tólemdi anıqlawǵa járdem beredi.",
}


def receipt_reply(lang: str, *, registration_succeeded: bool) -> str:
    """Answer a receipt request: the capability limit, then what the customer can do."""
    leads = _RECEIPT_LEAD_SUCCESS if registration_succeeded else _RECEIPT_LEAD
    lead = leads.get(lang) or leads["uz"]
    body = _RECEIPT_BODY.get(lang) or _RECEIPT_BODY["uz"]
    return f"{lead} {body}"


_FEE_LEAD_AMOUNT = {
    "uz": "Bu summa qanday shakllanganini aniqlash muhim.",
    "uz_cyrl": "Бу сумма қандай шаклланганини аниқлаш муҳим.",
    "ru": "Здесь важно понять, из чего система сформировала эту сумму.",
    "en": "The key thing is to understand how the system arrived at this amount.",
    "kaa": "Bul summa qalay qálipleskenin anıqlaw áhmiyetli.",
}
_FEE_LEAD = {
    "uz": "Registratsiya summasi qurilma qanday olib kirilgani va ro'yxatga olish toifasiga "
    "bog'liq.",
    "uz_cyrl": "Регистрация суммаси қурилма қандай олиб кирилгани ва рўйхатга олиш "
    "тоифасига боғлиқ.",
    "ru": "Сумма регистрации зависит от того, как устройство было ввезено, и от категории "
    "регистрации.",
    "en": "The registration charge depends on how the device came into the country and on "
    "its registration category.",
    "kaa": "Dizimge alıw summası qurılmanıń qalay alıp kirilgenine hám dizimge alıw "
    "túrine baylanıslı.",
}
_FEE_LIMIT = {
    "uz": "Men hisob-kitobni UZIMEI'da bevosita tekshira olmayman, lekin sababini tushunishga "
    "yordam beraman.",
    "uz_cyrl": "Мен ҳисоб-китобни UZIMEI'да бевосита текшира олмайман, лекин сабабини "
    "тушунишга ёрдам бераман.",
    "ru": "Я не могу проверить начисление напрямую в UZIMEI, но могу помочь разобраться.",
    "en": "I can't check the charge directly in UZIMEI, but I can help you work out why.",
    "kaa": "Men esap-kitaptı UZIMEI'de tikkeley tekserip bere almayman, biraq sebebin "
    "túsiniwge járdem beremen.",
}
_FEE_ORIGIN_Q = {
    "uz": "Telefonni chetdan o'zingiz olib kelganmisiz yoki O'zbekistonda sotib olganmisiz?",
    "uz_cyrl": "Телефонни четдан ўзингиз олиб келганмисиз ёки Ўзбекистонда сотиб олганмисиз?",
    "ru": "Подскажите, телефон вы привезли с собой из-за границы или купили уже в Узбекистане?",
    "en": "Did you bring the phone in from abroad yourself, or buy it in Uzbekistan?",
    "kaa": "Telefondı shet elden ózińiz alıp keldińizbe yamasa Ózbekstanda satıp aldıńızba?",
}
_FEE_IMPORTED = {
    "uz": "Chetdan olib kirilgan qurilmada summa olib kirish holatiga (deklaratsiya, nechta "
    "qurilma olib kirilgani) qarab farq qilishi mumkin — bu hozircha faqat taxmin. Aniq "
    "sababni bilish uchun summa tarkibi bo'yicha UZIMEI tizim operatoriga murojaat qiling; "
    "ariza raqami va summa ko'rsatilgan sahifa skrinshotini tayyorlang.",
    "uz_cyrl": "Четдан олиб кирилган қурилмада сумма олиб кириш ҳолатига (декларация, нечта "
    "қурилма олиб кирилгани) қараб фарқ қилиши мумкин — бу ҳозирча фақат тахмин. Аниқ "
    "сабабни билиш учун сумма таркиби бўйича UZIMEI тизим операторига мурожаат қилинг; "
    "ариза рақами ва сумма кўрсатилган саҳифа скриншотини тайёрланг.",
    "ru": "Для ввезённого устройства сумма может зависеть от обстоятельств ввоза "
    "(декларация, сколько устройств ввезено) — пока это лишь предположение. Чтобы узнать "
    "точную причину, обратитесь к оператору системы UZIMEI за расшифровкой суммы; "
    "подготовьте номер заявки и скриншот страницы с суммой.",
    "en": "For a device brought in from abroad, the amount can depend on how it was imported "
    "(declaration, how many devices were brought in) — that's only a hypothesis for now. "
    "To find the exact reason, ask the UZIMEI system operator for a breakdown of the "
    "amount; have the application number and a screenshot of the page showing it ready.",
    "kaa": "Shet elden alıp kirilgen qurılmada summa alıp kiriw jaǵdayına (deklaraciya, neshe "
    "qurılma alıp kirilgeni) qarap parıq qılıwı múmkin — bul házirshe tek boljaw. Anıq "
    "sebebin biliw ushın summa quramı boyınsha UZIMEI sistema operatorına múráját etiń.",
}
_FEE_LOCAL = {
    "uz": "Bilim bazasiga ko'ra, sotuv uchun olib kirilgan qurilmani import qiluvchi ro'yxatdan "
    "o'tkazishi kerak. Agar O'zbekistonda sotib olingan telefon uchun sizdan summa "
    "so'ralayotgan bo'lsa, buni sotuvchi va UZIMEI tizim operatori bilan aniqlashtiring; "
    "xarid chekini saqlab qo'ying.",
    "uz_cyrl": "Билим базасига кўра, сотув учун олиб кирилган қурилмани импорт қилувчи "
    "рўйхатдан ўтказиши керак. Агар Ўзбекистонда сотиб олинган телефон учун сиздан сумма "
    "сўралаётган бўлса, буни сотувчи ва UZIMEI тизим оператори билан аниқлаштиринг; "
    "харид чекини сақлаб қўйинг.",
    "ru": "По базе знаний устройство, ввезённое для продажи, должен регистрировать импортёр. "
    "Если за телефон, купленный в Узбекистане, с вас требуют оплату, уточните это у продавца "
    "и у оператора системы UZIMEI; сохраните чек о покупке.",
    "en": "According to the knowledge base, a device imported for sale should be registered "
    "by the importer. If you're being asked to pay for a phone bought in Uzbekistan, check "
    "this with the seller and the UZIMEI system operator, and keep the purchase receipt.",
    "kaa": "Bilim bazasına kóre, satıw ushın alıp kirilgen qurılmanı import etiwshi dizimnen "
    "ótkeriwi kerek. Eger Ózbekstanda satıp alınǵan telefon ushın sizden summa soralıp "
    "atırǵan bolsa, satıwshı hám UZIMEI sistema operatorı menen anıqlastırıń.",
}


def fee_reply(lang: str, *, amount_quoted: bool, device_origin: str | None) -> str:
    """Answer a fee complaint; ask the one deciding question only if it is unknown."""

    def pick(table: dict[str, str]) -> str:
        return table.get(lang) or table["uz"]

    lead = pick(_FEE_LEAD_AMOUNT if amount_quoted else _FEE_LEAD)
    if device_origin == "imported":
        return f"{lead} {pick(_FEE_LIMIT)} {pick(_FEE_IMPORTED)}"
    if device_origin == "local":
        return f"{lead} {pick(_FEE_LIMIT)} {pick(_FEE_LOCAL)}"
    return f"{lead} {pick(_FEE_LIMIT)} {pick(_FEE_ORIGIN_Q)}"


def fee_followup_reply(lang: str, device_origin: str) -> str:
    """The answer once the deciding fact (where the phone came from) is known."""
    table = _FEE_IMPORTED if device_origin == "imported" else _FEE_LOCAL
    return table.get(lang) or table["uz"]


# --- MNP: xato ko'chirish va ko'chirishdan keyingi rouming qarzi (3275-son Qoidalar) -------

_WRONG_PORT_REPLY = {
    "uz": "Bu oddiy MNP holati emas: raqamingiz siz soʻramasdan koʻchirilgan boʻlsa, bu xato "
    "(ehtimol ruxsatsiz) koʻchirish. 3275-son Qoidalarga koʻra (216-band) bunday raqamni "
    "qaytarish eski operatoringizga (donor) yozma ariza berish yoki uning maʼlumot xizmatiga "
    "murojaat qilish orqali boshlanadi, va sizning aybingiz boʻlmasa qaytarish uchun toʻlov "
    "olinmaydi. Raqam qaytarilgach xizmatlar, tarif rejasi va balans xato koʻchirishdan oldingi "
    "holatga tiklanadi (226-band). Men operator tizimlarini tekshira olmayman; murojaatda "
    "raqamingizni va aloqa qachon uzilganini koʻrsating. Agar shaxsiy maʼlumotlaringizdan "
    "ruxsatsiz foydalanilgan deb hisoblasangiz, buni ham arizada yozing.",
    "uz_cyrl": "Бу оддий MNP ҳолати эмас: рақамингиз сиз сўрамасдан кўчирилган бўлса, бу хато "
    "(эҳтимол рухсатсиз) кўчириш. 3275-сон Қоидаларга кўра (216-банд) бундай рақамни қайтариш "
    "эски операторингизга (донор) ёзма ариза бериш ёки унинг маълумот хизматига мурожаат қилиш "
    "орқали бошланади, ва сизнинг айбингиз бўлмаса қайтариш учун тўлов олинмайди. Рақам "
    "қайтарилгач хизматлар, тариф режаси ва баланс хато кўчиришдан олдинги ҳолатга тикланади "
    "(226-банд). Мен оператор тизимларини текшира олмайман; мурожаатда рақамингизни ва алоқа "
    "қачон узилганини кўрсатинг.",
    "ru": "Это не обычный перенос: если номер перенесли без вашей заявки, это ошибочный "
    "(возможно, несанкционированный) перенос. По Правилам № 3275 (п. 216) возврат такого номера "
    "начинается по вашему письменному заявлению прежнему оператору (донору) или обращению в его "
    "справочную службу, и если вашей вины нет, плата за возврат не взимается. После возврата "
    "услуги, тариф и баланс восстанавливаются на момент ошибочного переноса (п. 226). Я не могу "
    "проверить системы операторов; в обращении укажите номер и когда пропала связь. Если "
    "подозреваете использование ваших данных без согласия, укажите и это.",
    "en": "This isn't an ordinary port: if your number was moved without your request, it is "
    "a wrong (possibly unauthorised) port. Under Rules No. 3275 (clause 216), getting it back "
    "starts with a written application to your previous operator (the donor) or a call to its "
    "information service, and if you are not at fault there is no charge for the return. Once "
    "the number is returned, your services, tariff plan and balance are restored to their state "
    "before the wrong port (clause 226). I can't check operators' systems; in your application "
    "give the number and when the service stopped. If you think your personal data was misused, "
    "say so as well.",
    "kaa": "Bul ádettegi MNP emes: nomerińiz sizdiń talabıńızsız kóshirilgen bolsa, bul qáte "
    "(múmkin ruxsatsız) kóshiriw. 3275-san Qaǵıydalarǵa kóre (216-band) bunday nomerdi qaytarıw "
    "eski operatorıńızǵa (donor) jazba arza beriw yamasa onıń maǵlıwmat xızmetine múráját etiw "
    "arqalı baslanadı, hám sizdiń aybıńız bolmasa qaytarıw ushın tólem alınbaydı. Nomer "
    "qaytarılǵannan keyin xızmetler, tarif hám balans qáte kóshiriwden aldınǵı jaǵdayǵa "
    "tiklenedi (226-band).",
}

_ROAMING_DEBT_REPLY = {
    "uz": "Rouming qarzi koʻchirishni rad etish asosi emas: eski operator qarz yoʻqligini "
    "rouming xizmatlaridan tashqari tekshiradi (3275-son Qoidalar, 186-band). "
    "Koʻchirishdan keyin esa eski operator (donor) rouming xizmatlari uchun qarzni talab "
    "qilishi mumkin, lekin faqat koʻchirish sanasidan boshlab 30 kalendar kun ichida — bundan "
    "kech yuborilgan talabni KRMB operatori rad etadi (3275-son Qoidalar, 208-band). Talab "
    "tasdiqlansa, yangi operator 15 daqiqa ichida SMS orqali qarzni toʻlash kerakligini "
    "xabar qiladi; toʻlash muddati 7 ish kunidan oshmaydi. Shu muddatda toʻlanmasa, yangi "
    "operator qarz toʻliq toʻlanguncha xizmatni toʻxtatadi; toʻlangach eski operator 15 daqiqa "
    "ichida blokdan chiqarish haqida xabar beradi. SMS kelgan boʻlsa, qarzni eski operatorga "
    "toʻlang — raqamni qayta koʻchirish shart emas.",
    "uz_cyrl": "Роуминг қарзи кўчиришни рад этиш асоси эмас: эски оператор қарз йўқлигини "
    "роуминг хизматларидан ташқари текширади (186-банд). "
    "Кўчиришдан кейин эса эски оператор (донор) роуминг хизматлари учун қарзни талаб "
    "қилиши мумкин, лекин фақат кўчириш санасидан бошлаб 30 календар кун ичида — бундан кеч "
    "юборилган талабни KRMB оператори рад этади (3275-сон Қоидалар, 208-банд). Талаб "
    "тасдиқланса, янги оператор 15 дақиқа ичида SMS орқали хабар қилади; тўлаш муддати 7 иш "
    "кунидан ошмайди. Шу муддатда тўланмаса, янги оператор қарз тўлангунча хизматни "
    "тўхтатади; тўлангач эски оператор 15 дақиқа ичида блокдан чиқариш ҳақида хабар беради.",
    "ru": "Долг за роуминг не является основанием для отказа в переносе: донор проверяет "
    "отсутствие задолженности, кроме роуминга (Правила № 3275, п. 186). "
    "После переноса прежний оператор (донор) может выставить долг за роуминг, но только в "
    "течение 30 календарных дней с даты переноса — более поздний запрос KRMB отклоняет (Правила "
    "№ 3275, п. 208). Если запрос подтверждён, новый оператор в течение 15 минут сообщит по SMS о "
    "необходимости оплаты; срок оплаты — не более 7 рабочих дней. Если не оплатить в этот срок, "
    "новый оператор приостановит услуги до полной оплаты; после оплаты донор в течение 15 минут "
    "сообщает о разблокировке. Переносить номер заново не нужно.",
    "en": "A roaming debt is not a reason to reject porting: the donor checks for debts other "
    "than roaming (Rules No. 3275, clause 186). "
    "After porting, your previous operator (the donor) can still bill a roaming debt, but "
    "only within 30 calendar days of the porting date — a later request is rejected by KRMB "
    "(Rules No. 3275, clause 208). If the request is confirmed, your new operator notifies you "
    "by SMS within 15 minutes; the payment deadline is at most 7 working days. If it isn't paid "
    "in time, the new operator suspends service until the debt is paid in full; once paid, the "
    "donor reports the unblocking within 15 minutes. You don't need to port the number again.",
    "kaa": "Rouming qarızı kóshiriwdi biykar etiw tiykarı emes: eski operator qarızdı rouming "
    "xızmetlerinen tısqarı tekseredi (186-band). "
    "Kóshiriwden keyin de eski operator (donor) rouming xızmetleri ushın qarızdı talap "
    "etiwi múmkin, biraq tek kóshiriw sánesinen baslap 30 kalendar kún ishinde (3275-san "
    "Qaǵıydalar, 208-band). Talap tastıyıqlansa, jańa operator 15 minut ishinde SMS arqalı "
    "xabar beredi; tólew múddeti 7 jumıs kúninen aspaydı. Tólenbese, jańa operator qarız "
    "tólengenshe xızmetti toqtatadı.",
}


def wrong_port_reply(lang: str) -> str:
    """A number ported without the customer's request: the return procedure (216, 226)."""
    return _WRONG_PORT_REPLY.get(lang) or _WRONG_PORT_REPLY["uz"]


def roaming_debt_reply(lang: str) -> str:
    """A roaming debt and MNP: not a rejection ground (186); billed after porting (208)."""
    return _ROAMING_DEBT_REPLY.get(lang) or _ROAMING_DEBT_REPLY["uz"]
