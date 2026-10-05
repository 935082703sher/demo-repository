"""Case reasoning endpoints.

/assistant/understand builds the structured CaseState from a free-form story
(fact extraction). /assistant/converse is the full conversation brain: it greets
small talk, routes a topic, extracts facts, and walks the decision tree as a
fact guardrail - auto-skipping any question whose answer the user already gave and
asking only the next missing one, until an approved resolution card is reached.
It never invents facts.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus, Outcome
from app.domain.diagnostics import DecisionTree, DiagnosticNode, ResolutionCard
from app.domain.enums import Category, Language
from app.domain.schemas import LLMRequest
from app.providers.base import LLMProvider
from app.providers.errors import ProviderError
from app.services.audit_log import (
    OUTCOME_ANSWER,
    OUTCOME_CLARIFY,
    OUTCOME_GREETING,
    OUTCOME_HANDOFF,
    OUTCOME_QUESTION,
    OUTCOME_RESOLVED,
    ROUTE_CASE,
    ROUTE_GREETING,
    ROUTE_RAG,
    AuditEvent,
    AuditLog,
)
from app.services.card_explainer import CardExplainer
from app.services.case_store import CaseStore
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.fact_extraction import (
    IMEI_FACT_FIELDS,
    MNP_FACT_FIELDS,
    FactExtractor,
    detect_domain,
    strong_domain,
)
from app.services.grounding import GroundingValidator
from app.services.interaction_log import InteractionLog, InteractionRecord
from app.services.kb_retriever import get_retriever
from app.services.localizer import Localizer
from app.services.outcome_analyzer import OutcomeAnalysis, OutcomeAnalyzer
from app.services.pii import redact_likely_pii
from app.services.question_explainer import QuestionExplainer
from app.services.resolution_orchestrator import (
    AWAITING_OUTCOME,
    CALL_1170_REQUESTED,
    OrchestratorDecision,
    ResolutionOrchestrator,
)
from app.services.router import Route
from app.services.turn_analysis import TurnAnalyzer

router = APIRouter(prefix="/assistant", tags=["case"])


# --- /assistant/understand: story -> facts (no conversation control) -----------


class UnderstandRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=100)
    language: str = Field(default="uz", pattern="^(uz|uz_cyrl|ru|en|kaa)$")
    channel: str = Field(default="web", pattern="^(web|telegram)$")


class FactOut(BaseModel):
    name: str
    value: str | None
    status: str
    confidence: float
    source: str


class UnderstandResponse(BaseModel):
    case_id: str
    session_id: str
    domain: str | None
    status: str
    turn_count: int
    known_facts: dict[str, str]
    unknown_facts: list[str]
    facts: list[FactOut]


def _refresh_unknowns(case: CaseState) -> None:
    fields = {"imei": IMEI_FACT_FIELDS, "mnp": MNP_FACT_FIELDS}.get(case.domain or "")
    if fields is not None:
        case.unknown_facts = [name for name in fields if not case.has(name)]


@router.post("/understand", response_model=UnderstandResponse)
async def assistant_understand(payload: UnderstandRequest, request: Request) -> UnderstandResponse:
    """Update the session's case with facts extracted from this message."""
    store = cast(CaseStore, request.app.state.case_store)
    extractor = cast(FactExtractor, request.app.state.fact_extractor)

    case = await store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1
    message = redact_likely_pii(payload.message)  # never store or extract from raw PII
    if case.domain is None:
        case.domain = detect_domain(message)
    for fact in await extractor.extract(message, case, turn_id=case.turn_count):
        case.upsert(fact)
    _refresh_unknowns(case)
    await store.save(case)

    return UnderstandResponse(
        case_id=case.case_id,
        session_id=case.session_id,
        domain=case.domain,
        status=case.status.value,
        turn_count=case.turn_count,
        known_facts=case.known_facts(),
        unknown_facts=case.unknown_facts,
        facts=[
            FactOut(
                name=fact.name,
                value=fact.value,
                status=fact.status.value,
                confidence=fact.confidence,
                source=fact.source,
            )
            for fact in case.facts.values()
        ],
    )


# --- /assistant/converse: the full conversation brain --------------------------

_GREETING = {
    "uz": "Assalomu alaykum! Men IMEI va MNP bo'yicha yordam beraman. Muammoingizni "
    "o'z so'zlaringiz bilan yozing — masalan «telefonim chetdan, ro'yxatdan o'tmayapti» "
    "yoki «raqamni boshqa operatorga ko'chirmoqchiman».",
    "uz_cyrl": "Ассалому алайкум! Мен IMEI ва MNP бўйича ёрдам бераман. Муаммоингизни "
    "ўз сўзларингиз билан ёзинг — масалан «телефоним четдан, рўйхатдан ўтмаяпти» "
    "ёки «рақамни бошқа операторга кўчирмоқчиман».",
    "ru": "Здравствуйте! Я помогаю по IMEI и MNP. Опишите проблему своими словами — "
    "например «телефон из-за границы, не регистрируется» или «хочу перенести номер».",
    "en": "Hello! I help with IMEI and MNP. Describe your problem in your own words.",
    "kaa": "Assalawma áleykum! Men IMEI hám MNP boyınsha járdem beremen. Máseleńizdi óz "
    "sózlerińiz benen jazıń — mısalı «telefonım shet elden, dizimnen ótpey atır» "
    "yáki «nomerimdi basqa operatorǵa kóshirmekshimen».",
}
_ROUTE_INTRO = {
    "uz": "Muammoingizni aniqlashtiraylik. Quyidagilardan mos bo'lganini tanlang:",
    "uz_cyrl": "Муаммоингизни аниқлаштирайлик. Қуйидагилардан мос бўлганини танланг:",
    "ru": "Уточним вашу проблему. Выберите подходящий пункт:",
    "en": "Let's narrow it down. Please pick the closest option:",
    "kaa": "Máseleńizdi anıqlastırayıq. Tómendegilerden sáykesin saylań:",
}
_DOMAIN_INTRO = {
    "uz": {
        "imei": "IMEI bo'yicha aynan qanday yordam kerak?",
        "mnp": "MNP bo'yicha aynan qanday yordam kerak?",
    },
    "uz_cyrl": {
        "imei": "IMEI бўйича айнан қандай ёрдам керак?",
        "mnp": "MNP бўйича айнан қандай ёрдам керак?",
    },
    "ru": {"imei": "Что именно нужно по IMEI?", "mnp": "Что именно нужно по MNP?"},
    "kaa": {
        "imei": "IMEI boyınsha tap qanday járdem kerek?",
        "mnp": "MNP boyınsha tap qanday járdem kerek?",
    },
}
_HANDOFF_REPLY = {
    "uz": "Bu masalani mutaxassisga yo'naltiraman.",
    "uz_cyrl": "Бу масалани мутахассисга йўналтираман.",
    "ru": "Передаю вопрос специалисту.",
    "en": "I'll route this to a specialist.",
    "kaa": "Bul máseleni qániygege jiberemen.",
}
_RAG_TOP_K = 5
# BM25 relevance floor: below this the top hit is too weak to answer from, so the
# assistant abstains instead of answering from irrelevant evidence. Calibrated on
# the corpus - on-topic queries score well above it, off-topic ones well below.
_RAG_MIN_SCORE = 4.0
# The grounded-answer request carries the base enum; the exact script/language is
# steered by a short hint prepended to the question (see _rag_answer).
_LANG_ENUM = {
    "uz": Language.UZ,
    "uz_cyrl": Language.UZ,
    "ru": Language.RU,
    "en": Language.EN,
    "kaa": Language.UZ,
}
_ANSWER_LANG_HINT = {
    "uz_cyrl": "(Write the answer in Uzbek using the CYRILLIC alphabet.) ",
    "kaa": "(Write the answer in the Karakalpak language.) ",
}
_CATEGORY_BY_DOMAIN = {
    "imei": Category.IMEI,
    "mnp": Category.MNP,
    "aloqa_sifati": Category.NETWORK_QUALITY,
}
_NO_EVIDENCE_REPLY = {
    "uz": "Bu savolga tasdiqlangan manbadan aniq javob topa olmadim. Mutaxassisga yo'naltiraman.",
    "uz_cyrl": "Бу саволга тасдиқланган манбадан аниқ жавоб топа олмадим. "
    "Мутахассисга йўналтираман.",
    "ru": "Не нашёл точного ответа в проверенных источниках. Передаю специалисту.",
    "en": "I couldn't find a confirmed source for this. I'll route you to a specialist.",
    "kaa": "Bul sorawǵa tastıyıqlanǵan derekten anıq juwap taba almadım. Qániygege jiberemen.",
}
_RAG_CLARIFY = {
    "uz": "Bunga aniq javob topa olmadim. Men IMEI va MNP bo'yicha yordam beraman — "
    "quyidagi mavzulardan birini tanlang yoki 1170 ga murojaat qiling:",
    "uz_cyrl": "Бунга аниқ жавоб топа олмадим. Мен IMEI ва MNP бўйича ёрдам бераман — "
    "қуйидаги мавзулардан бирини танланг ёки 1170 га мурожаат қилинг:",
    "ru": "Я не нашёл точного ответа. Я помогаю по IMEI и MNP — выберите тему ниже "
    "или обратитесь на 1170:",
    "en": "I couldn't find an exact answer. I help with IMEI and MNP — pick a topic "
    "below, or call 1170:",
    "kaa": "Buǵan anıq juwap taba almadım. Men IMEI hám MNP boyınsha járdem beremen — "
    "tómendegi temalardan birin saylań yáki 1170 ge xabarlasıń:",
}


class ConverseCaseRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=100)
    language: str = Field(default="uz", pattern="^(uz|uz_cyrl|ru|en|kaa)$")
    channel: str = Field(default="web", pattern="^(web|telegram)$")


class OptionOut(BaseModel):
    value: str
    label: str


class SourceOut(BaseModel):
    doc_id: str
    title: str


class ImageOut(BaseModel):
    url: str
    caption: str


# Approved UZIMEI screenshots shown with the matching resolution, so the user sees
# exactly which block to use on the site.
_IMG_REGISTER = ImageOut(
    url="/media/uzimei-register.png", caption="IMEI onlayn ro'yxatdan o'tkazish"
)
_IMG_PAYMENT = ImageOut(url="/media/uzimei-payment.png", caption="Ariza raqami bo'yicha to'lov")
_CARD_IMAGES: dict[str, list[ImageOut]] = {
    "imei-register": [_IMG_REGISTER, _IMG_PAYMENT],
    "imei-customs": [_IMG_REGISTER, _IMG_PAYMENT],
    "imei-clone": [_IMG_REGISTER],
}


class ConverseCaseResponse(BaseModel):
    reply: str
    options: list[OptionOut]
    done: bool
    card_id: str | None
    domain: str | None
    known_facts: dict[str, str]
    unknown_facts: list[str]
    requires_human: bool
    sources: list[SourceOut] = []
    images: list[ImageOut] = []
    status: str | None = None
    call_1170: bool = False
    phone: str | None = None


async def _audit(
    audit: AuditLog,
    case: CaseState,
    outcome: str,
    route: str,
    *,
    card_id: str | None = None,
    tree_id: str | None = None,
) -> None:
    """Record one converse turn for the KPI metrics."""
    await audit.record(
        AuditEvent(
            channel=case.channel,
            language=case.language,
            outcome=outcome,
            category=case.domain,
            tree_id=tree_id,
            card_id=card_id,
            session_id=case.session_id,
            route=route,
        )
    )


def _start_fresh_case(case: CaseState) -> None:
    """Clear the diagnostic slate for a new problem, keeping the session identity.

    Once a case is resolved or handed off, the next message is a new problem: its
    facts must not be auto-completed by the previous case's facts. Session id,
    turn count, language and channel are preserved.
    """
    case.facts.clear()
    case.unknown_facts = []
    case.candidate_issues = []
    case.domain = None
    case.diagnosis = None
    case.diagnosis_confidence = None
    case.resolution_card_id = None
    case.active_tree = None
    case.pending_node = None
    case.status = CaseStatus.UNDERSTANDING
    # A new problem starts with a clean resolution lifecycle, but the explanation
    # profile (how this person likes to be talked to) is kept across problems.
    case.current_cause = None
    case.excluded_causes = []
    case.remaining_causes = []
    case.tried_card_ids = []
    case.attempts = []
    case.last_question = None
    case.last_customer_reply = None
    case.call_1170_reason = None


def _resp(
    case: CaseState,
    reply: str,
    *,
    options: list[OptionOut] | None = None,
    done: bool = False,
    card_id: str | None = None,
    requires_human: bool = False,
    sources: list[SourceOut] | None = None,
    call_1170: bool = False,
    phone: str | None = None,
) -> ConverseCaseResponse:
    return ConverseCaseResponse(
        reply=reply,
        options=options or [],
        done=done,
        card_id=card_id,
        domain=case.domain,
        known_facts=case.known_facts(),
        unknown_facts=case.unknown_facts,
        requires_human=requires_human,
        sources=sources or [],
        images=_CARD_IMAGES.get(card_id or "", []),
        status=case.status.value,
        call_1170=call_1170,
        phone=phone,
    )


# Languages the trees/cards have no native labels for, so menu titles and answer
# buttons (never facts) are translated on demand; uz/ru/en resolve from the data.
_LOCALIZE_LANGS = {"uz_cyrl", "kaa"}


async def _localize_labels(localizer: Localizer, labels: list[str], lang: str) -> list[str]:
    """Translate navigation labels for a script the data has no native text for."""
    if lang not in _LOCALIZE_LANGS or not labels:
        return labels
    return await localizer.localize(labels, lang)


async def _menu(
    case: CaseState,
    trees: list[DecisionTree],
    intro: str,
    lang: str,
    localizer: Localizer,
) -> ConverseCaseResponse:
    labels = await _localize_labels(localizer, [tree.title.get(lang) for tree in trees], lang)
    options = [
        OptionOut(value=tree.id, label=label) for tree, label in zip(trees, labels, strict=True)
    ]
    return _resp(case, intro, options=options)


_STEPS_HEADER = {
    "uz": "Qadamlar:",
    "uz_cyrl": "Қадамлар:",
    "ru": "Шаги:",
    "en": "Steps:",
    "kaa": "Qádemler:",
}
_WHERE_LABEL = {
    "uz": "Qayerga",
    "uz_cyrl": "Қаерга",
    "ru": "Куда обратиться",
    "en": "Where",
    "kaa": "Qayerge",
}
_DOCS_HEADER = {
    "uz": "Kerakli hujjatlar:",
    "uz_cyrl": "Керакли ҳужжатлар:",
    "ru": "Нужные документы:",
    "en": "Documents needed:",
    "kaa": "Kerekli hújjetler:",
}


async def _card_reply(
    explainer: CardExplainer, card: ResolutionCard, case: CaseState, lang: str
) -> str:
    """Compose the full resolution: an LLM-explained cause, then the exact approved
    steps, required documents, where to apply, link and contact (never touched by
    the LLM). Surfacing every approved field answers the likely follow-ups up front."""
    cause = await explainer.explain(card.probable_cause.get(lang), case, lang)
    lines = [cause, "", _STEPS_HEADER.get(lang, _STEPS_HEADER["uz"])]
    lines += [f"{index}. {step.get(lang)}" for index, step in enumerate(card.steps, 1)]
    if card.documents:
        lines.append("")
        lines.append(_DOCS_HEADER.get(lang, _DOCS_HEADER["uz"]))
        lines += [f"• {doc.get(lang)}" for doc in card.documents]
    if card.where_to_apply:
        where_label = _WHERE_LABEL.get(lang, _WHERE_LABEL["uz"])
        lines.append(f"{where_label}: {card.where_to_apply.get(lang)}")
    if card.official_url:
        lines.append("🔗 " + card.official_url)
    if card.contact:
        lines.append("📞 " + card.contact)
    return "\n".join(lines)


# --- Resolution lifecycle rendering (BLOK: offer -> result -> alternative / 1170) ---

# Result buttons shown under an offered card; values are read back as outcomes.
_RESULT_SUCCESS = "outcome:success"
_RESULT_FAILURE = "outcome:failure"
_RESULT_UNCLEAR = "outcome:unclear"
_RESULT_LABELS = {
    "uz": [
        ("Ha, hal bo'ldi", _RESULT_SUCCESS),
        ("Yo'q, muammo qoldi", _RESULT_FAILURE),
        ("Tushunmadim", _RESULT_UNCLEAR),
    ],
    "uz_cyrl": [
        ("Ҳа, ҳал бўлди", _RESULT_SUCCESS),
        ("Йўқ, муаммо қолди", _RESULT_FAILURE),
        ("Тушунмадим", _RESULT_UNCLEAR),
    ],
    "ru": [
        ("Да, решилось", _RESULT_SUCCESS),
        ("Нет, проблема осталась", _RESULT_FAILURE),
        ("Не понял", _RESULT_UNCLEAR),
    ],
    "en": [
        ("Yes, it's fixed", _RESULT_SUCCESS),
        ("No, still a problem", _RESULT_FAILURE),
        ("I didn't understand", _RESULT_UNCLEAR),
    ],
    "kaa": [
        ("Awa, sheshildi", _RESULT_SUCCESS),
        ("Yaq, másele qaldı", _RESULT_FAILURE),
        ("Túsinbedim", _RESULT_UNCLEAR),
    ],
}
_RESOLVED_REPLY = {
    "uz": "Zo'r! Muammo hal bo'lganiga xursandman. Yana savol bo'lsa, yozavering.",
    "uz_cyrl": "Зўр! Муаммо ҳал бўлганига хурсандман. Яна савол бўлса, ёзаверинг.",
    "ru": "Отлично! Рад, что проблема решилась. Если будут вопросы — пишите.",
    "en": "Great! I'm glad it's resolved. Write again if anything else comes up.",
    "kaa": "Zor! Máseleniń sheshilgenine quwanaman. Taǵı sorawıńız bolsa, jazıń.",
}
_REQUEST_EVIDENCE = {
    "uz": "Aniqlashtirish uchun: ekranda yoki SMSda chiqqan xato matnini yozib yuboring "
    "(shaxsiy ma'lumotlarni yopib qo'ying).",
    "uz_cyrl": "Аниқлаштириш учун: экранда ёки SMSда чиққан хато матнини ёзиб юборинг "
    "(шахсий маълумотларни ёпиб қўйинг).",
    "ru": "Чтобы уточнить: пришлите текст ошибки с экрана или из SMS (личные данные закройте).",
    "en": "To narrow it down: send the exact error text from the screen or SMS "
    "(hide any personal data).",
    "kaa": "Anıqlaw ushın: ekranda yaki SMSda shıqqan qáte matnin jazıń "
    "(jeke maǵlıwmatlardı jawıp qoyıń).",
}
_PARTIAL_CLARIFY = {
    "uz": "Qaysi qism hali ham hal bo'lmayapti? Qisqa yozing.",
    "uz_cyrl": "Қайси қисм ҳали ҳам ҳал бўлмаяпти? Қисқа ёзинг.",
    "ru": "Какая часть ещё не решена? Напишите коротко.",
    "en": "Which part is still not resolved? A short note is enough.",
    "kaa": "Qaysı bólim ele sheshilmedi? Qısqa jazıń.",
}
_CHECK_QUESTION = {
    "uz": "Shu qadamni bajarib ko'ring. Muammo hal bo'ldimi?",
    "uz_cyrl": "Шу қадамни бажариб кўринг. Муаммо ҳал бўлдими?",
    "ru": "Выполните этот шаг. Проблема решилась?",
    "en": "Try this step. Did it fix the problem?",
    "kaa": "Usı qádemdi orınlań. Másele sheshildi me?",
}
# 1170 summary wrapper; the tried-step list and the operator script are filled in.
_CALL_1170 = {
    "uz": (
        "Mavjud xavfsiz yechimlarni tekshirdik, ammo muammo saqlanib qoldi.\n\n"
        "Tekshirilganlar:\n{tried}\n\n"
        "Bu holat individual tekshiruvni talab qiladi. {phone} raqamiga qo'ng'iroq qiling.\n\n"
        "Operatorga shunday ayting: «{script}»."
    ),
    "ru": (
        "Мы проверили доступные безопасные решения, но проблема осталась.\n\n"
        "Проверено:\n{tried}\n\n"
        "Этот случай требует индивидуальной проверки. Позвоните по номеру {phone}.\n\n"
        "Скажите оператору: «{script}»."
    ),
    "en": (
        "We tried the available safe fixes, but the problem remains.\n\n"
        "Checked:\n{tried}\n\n"
        "This needs an individual review. Please call {phone}.\n\n"
        'Tell the operator: "{script}".'
    ),
}
_CALL_1170_SCRIPT = {
    "uz": "Muammoni hal qila olmadim, sinab ko'rilgan qadamlar yordam bermadi",
    "ru": "Не смог решить проблему, выполненные шаги не помогли",
    "en": "I couldn't resolve the issue; the steps I tried did not help",
}


def _result_options(lang: str) -> list[OptionOut]:
    labels = _RESULT_LABELS.get(lang, _RESULT_LABELS["uz"])
    return [OptionOut(value=value, label=text) for text, value in labels]


def _result_from_value(value: str) -> Outcome | None:
    """Map a result button value to an Outcome, or None for free text."""
    return {
        _RESULT_SUCCESS: Outcome.SUCCESS,
        _RESULT_FAILURE: Outcome.FAILURE,
        _RESULT_UNCLEAR: Outcome.UNCLEAR,
    }.get(value)


async def _offer_reply(
    explainer: CardExplainer, card: ResolutionCard, case: CaseState, lang: str
) -> str:
    """The card's full resolution text followed by its success-check question."""
    body = await _card_reply(explainer, card, case, lang)
    check = card.success_check
    question = (
        check.question.get(lang) if check and check.question else None
    ) or _CHECK_QUESTION.get(lang, _CHECK_QUESTION["uz"])
    return f"{body}\n\n{question}"


def _build_1170_reply(case: CaseState, engine: DiagnosticEngine, lang: str, phone: str) -> str:
    """A useful summary before the 1170 number: what was checked and what to say."""
    template = _CALL_1170.get(lang, _CALL_1170["uz"])
    tried_titles: list[str] = []
    for card_id in case.tried_card_ids:
        card = engine.get_card(card_id)
        title = card.title.get(lang) if card else card_id
        if title not in tried_titles:
            tried_titles.append(title)
    tried = "\n".join(f"• {title}" for title in tried_titles) or "• —"
    script = _CALL_1170_SCRIPT.get(lang, _CALL_1170_SCRIPT["uz"])
    return template.format(tried=tried, phone=phone, script=script)


def _apply_option(engine: DiagnosticEngine, case: CaseState, value: str) -> ResolutionCard | None:
    """Apply the chosen option on the pending node: set its fact, advance/resolve."""
    node = engine.get_node(case.active_tree or "", case.pending_node or "")
    if node is None:
        return None
    option = next((o for o in node.options if o.value == value), None)
    if option is None:
        return None
    if node.fact and option.fact_value:
        case.upsert(
            Fact(
                name=node.fact,
                value=option.fact_value,
                status=FactStatus.EXPLICIT,
                source="answer",
                turn_id=case.turn_count,
            )
        )
    if option.card is not None:
        # Record which card the answer leads to; the caller finalizes it (a one-shot
        # card is closed; a lifecycle card is offered with its active tree kept so an
        # alternative can be found later).
        case.resolution_card_id = option.card
        return engine.get_card(option.card)
    if option.next_node is not None:
        case.pending_node = option.next_node
    return None


def _has_strong_evidence(results: list[Any], min_score: float) -> bool:
    """True when the top retrieved passage clears the relevance floor."""
    return bool(results) and results[0].score >= min_score


async def _log_unanswered(log: InteractionLog | None, case: CaseState, message: str) -> None:
    """Record a question the knowledge base could not answer, for the review list."""
    if log is None:
        return
    await log.record(
        InteractionRecord(
            session_id=case.session_id,
            channel=case.channel,
            language=case.language,
            kind="unanswered",
            outcome="unanswered",
            message=message,
            domain=case.domain,
            requires_human=True,
        )
    )


async def _rag_answer(
    provider: LLMProvider,
    grounding: GroundingValidator,
    log: InteractionLog | None,
    case: CaseState,
    message: str,
    lang: str,
) -> ConverseCaseResponse:
    """Answer an informational question strictly from approved KB evidence.

    Retrieves the top approved passages and lets the provider answer only from
    them. It abstains - never invents an answer - when there is no evidence, the
    top hit is too weak, the provider fails, or the answer cites a source it was
    not given (grounding check). A KB gap (no/weak evidence or an ungroundable
    answer) is also recorded as an 'unanswered' question so it can be reviewed and
    answered later. Sources are returned only when it actually answers.
    """
    retriever = get_retriever()
    results = retriever.retrieve(message, _RAG_TOP_K, domain=case.domain)
    fallback = _NO_EVIDENCE_REPLY.get(lang, _NO_EVIDENCE_REPLY["uz"])
    # Abstain when there is no evidence or the best hit is too weak to trust.
    if not _has_strong_evidence(results, _RAG_MIN_SCORE):
        await _log_unanswered(log, case, message)
        return _resp(case, fallback, done=True, requires_human=True)
    source_ids = [r.chunk.doc_id for r in results]
    llm_request = LLMRequest(
        language=_LANG_ENUM.get(lang, Language.UZ),
        question=_ANSWER_LANG_HINT.get(lang, "") + message,
        category=_CATEGORY_BY_DOMAIN.get(results[0].chunk.domain, Category.OTHER),
        source_ids=source_ids,
        passages=[r.chunk.text for r in results],
    )
    try:
        result = await provider.generate(llm_request)
    except ProviderError:
        return _resp(case, fallback, done=True, requires_human=True)  # technical, not a KB gap
    # Grounding: the answer must cite only sources it was actually given.
    if not grounding.authorize(result.text, result.citations, source_ids):
        await _log_unanswered(log, case, message)
        return _resp(case, fallback, done=True, requires_human=True)
    sources = [SourceOut(doc_id=r.chunk.doc_id, title=r.chunk.title) for r in results]
    return _resp(case, result.text, done=True, sources=sources)


async def _render_decision(
    decision: OrchestratorDecision,
    case: CaseState,
    *,
    engine: DiagnosticEngine,
    explainer: CardExplainer,
    q_explainer: QuestionExplainer,
    localizer: Localizer,
    lang: str,
    phone: str,
) -> ConverseCaseResponse:
    """Turn one orchestrator decision into the customer-facing response."""
    if decision.kind == "resolved":
        card_id = decision.card.id if decision.card else None
        return _resp(
            case, _RESOLVED_REPLY.get(lang, _RESOLVED_REPLY["uz"]), done=True, card_id=card_id
        )
    if decision.kind == "call_1170":
        reply = _build_1170_reply(case, engine, lang, phone)
        return _resp(case, reply, done=True, requires_human=True, call_1170=True, phone=phone)
    if decision.kind in ("offer_card", "reexplain") and decision.card is not None:
        reply = await _offer_reply(explainer, decision.card, case, lang)
        return _resp(
            case, reply, options=_result_options(lang), card_id=decision.card.id, done=False
        )
    if decision.kind == "request_evidence":
        return _resp(case, _REQUEST_EVIDENCE.get(lang, _REQUEST_EVIDENCE["uz"]), done=False)
    if decision.kind == "ask_node" and decision.node is not None:
        node = decision.node
        question = await q_explainer.explain(node.question.get(lang), case, lang)
        labels = await _localize_labels(localizer, [o.label.get(lang) for o in node.options], lang)
        options = [
            OptionOut(value=o.value, label=label)
            for o, label in zip(node.options, labels, strict=True)
        ]
        return _resp(case, question, options=options, done=False)
    # clarify / fallback: ask what remains without closing the case.
    return _resp(case, _PARTIAL_CLARIFY.get(lang, _PARTIAL_CLARIFY["uz"]), done=False)


# Phrases where the customer asks for phone help directly (then 1170 is appropriate).
_PHONE_REQUEST = (
    "1170",
    "qongiroq",
    "qo'ng'iroq",
    "telefon qil",
    "operator",
    "jonli",
    "позвони",
    "оператор",
    "call ",
    "phone",
)


def _wants_phone(message: str) -> bool:
    """True when the customer explicitly asks for phone/operator help."""
    low = message.lower()
    return any(term in low for term in _PHONE_REQUEST)


def _lifecycle_audit(decision: OrchestratorDecision) -> str:
    """Map a lifecycle decision to an audit outcome label."""
    if decision.kind == "resolved":
        return OUTCOME_RESOLVED
    if decision.kind == "call_1170":
        return OUTCOME_HANDOFF
    return OUTCOME_QUESTION


async def _finalize_card(
    card: ResolutionCard,
    case: CaseState,
    *,
    engine: DiagnosticEngine,
    orchestrator: ResolutionOrchestrator,
    explainer: CardExplainer,
    q_explainer: QuestionExplainer,
    localizer: Localizer,
    store: CaseStore,
    audit: AuditLog,
    lang: str,
    phone: str,
    tree_id: str | None = None,
) -> ConverseCaseResponse:
    """Offer a reached card through the lifecycle, or close it as a one-shot answer.

    A card with a success_check enters the result-tracking loop (offered, then its
    result awaited); any other card keeps the previous behaviour: closed at once.
    """
    if orchestrator.uses_lifecycle(card):
        if tree_id and case.active_tree is None:
            case.active_tree = tree_id  # keep the tree so alternatives can be found
        decision = orchestrator.offer_card(case, card)
        await store.save(case)
        await _audit(audit, case, OUTCOME_QUESTION, ROUTE_CASE, card_id=card.id, tree_id=tree_id)
        return await _render_decision(
            decision,
            case,
            engine=engine,
            explainer=explainer,
            q_explainer=q_explainer,
            localizer=localizer,
            lang=lang,
            phone=phone,
        )
    case.active_tree = None
    case.pending_node = None
    case.resolution_card_id = card.id
    case.status = CaseStatus.RESOLVED
    await store.save(case)
    await _audit(audit, case, OUTCOME_RESOLVED, ROUTE_CASE, card_id=card.id, tree_id=tree_id)
    card_text = await _card_reply(explainer, card, case, lang)
    return _resp(case, card_text, done=True, card_id=card.id)


async def _converse_turn(payload: ConverseCaseRequest, request: Request) -> ConverseCaseResponse:
    """One conversation turn: greet, route, extract facts, ask only what's missing."""
    store = cast(CaseStore, request.app.state.case_store)
    analyzer = cast(TurnAnalyzer, request.app.state.turn_analyzer)
    engine = cast(DiagnosticEngine, request.app.state.diagnostic_engine)
    provider = cast(LLMProvider, request.app.state.provider)
    explainer = cast(CardExplainer, request.app.state.card_explainer)
    q_explainer = cast(QuestionExplainer, request.app.state.question_explainer)
    localizer = cast(Localizer, request.app.state.localizer)
    grounding = cast(GroundingValidator, request.app.state.grounding)
    audit = cast(AuditLog, request.app.state.audit_log)
    interaction_log = cast(InteractionLog, getattr(request.app.state, "interaction_log", None))
    orchestrator = cast(ResolutionOrchestrator, request.app.state.resolution_orchestrator)
    outcome_analyzer = cast(OutcomeAnalyzer, request.app.state.outcome_analyzer)
    phone = str(
        getattr(getattr(request.app.state, "settings", None), "approved_support_phone", None)
        or "1170"
    )

    case = await store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1
    lang = payload.language
    # Redact PII up front: nothing raw reaches the LLM, the KB, the persisted case
    # or the logs. Only labelled/structured identifiers are redacted, so tariffs
    # and short official numbers pass through untouched.
    message = redact_likely_pii(payload.message)

    # A previously closed case starts fresh so old facts don't auto-complete a new one.
    if case.status in (CaseStatus.RESOLVED, CaseStatus.HANDOFF, CaseStatus.CALL_1170_RECOMMENDED):
        _start_fresh_case(case)

    # 0) A case awaiting a result: this message is the outcome of the offered card,
    #    not a new problem. Classify it and let the orchestrator decide what's next.
    if case.status in AWAITING_OUTCOME and case.resolution_card_id:
        case.last_customer_reply = message
        card = engine.get_card(case.resolution_card_id)
        forced = _result_from_value(payload.message.strip())
        if forced is None and _wants_phone(message):
            decision = orchestrator.recommend_1170(case, CALL_1170_REQUESTED)
        else:
            if forced is not None:
                outcome = OutcomeAnalysis(outcome=forced, confidence=1.0)
            else:
                check = card.success_check if card else None
                outcome = await outcome_analyzer.analyze(
                    message, case, check=check, turn_id=case.turn_count
                )
            for fact in outcome.extracted_facts:
                case.upsert(fact)
            decision = orchestrator.advance(case, outcome)
        await store.save(case)
        await _audit(
            audit, case, _lifecycle_audit(decision), ROUTE_CASE, card_id=card.id if card else None
        )
        return await _render_decision(
            decision,
            case,
            engine=engine,
            explainer=explainer,
            q_explainer=q_explainer,
            localizer=localizer,
            lang=lang,
            phone=phone,
        )

    # 1) Understand the message every turn (route + facts in one LLM call), so a
    #    new story is never ignored.
    analysis = await analyzer.analyze(message, case, turn_id=case.turn_count)
    for fact in analysis.facts:
        case.upsert(fact)
    if case.domain is None:
        # The analyzer's domain understands typos/dialect; keyword detection is the net.
        case.domain = analysis.domain or detect_domain(message)
    _refresh_unknowns(case)

    # 2) If a question is open and this message answers it, take that answer.
    answered = False
    if case.active_tree and case.pending_node:
        value = engine.map_answer(case.active_tree, case.pending_node, message)
        if value is not None:
            resolved = _apply_option(engine, case, value)
            if resolved is not None:
                _refresh_unknowns(case)
                return await _finalize_card(
                    resolved,
                    case,
                    engine=engine,
                    orchestrator=orchestrator,
                    explainer=explainer,
                    q_explainer=q_explainer,
                    localizer=localizer,
                    store=store,
                    audit=audit,
                    lang=lang,
                    phone=phone,
                    tree_id=case.active_tree,
                )
            answered = True

    # 3) Not an answer to an open question: pick the lane for this message.
    if not answered:
        # Constrain routing to the known domain so another domain's keyword cannot
        # hijack the message (e.g. "o'tkazmoqchi" vs the rejection word "otkaz").
        matched, route_domain = engine.route(message, domain=case.domain)
        chosen = (
            engine.get_tree(message.strip())
            or matched
            or engine.tree_from_facts(case.known_facts(), domain=case.domain)
        )

        # 3a) A curated resolution card the facts already complete beats everything:
        #     an approved answer (e.g. mnp-docs, imei-customs) wins over free RAG.
        if chosen is not None:
            kind, obj = engine.advance(chosen.id, chosen.root, case.known_facts())
            if kind == "resolve" and isinstance(obj, ResolutionCard):
                if case.domain is None:
                    case.domain = chosen.domain
                return await _finalize_card(
                    obj,
                    case,
                    engine=engine,
                    orchestrator=orchestrator,
                    explainer=explainer,
                    q_explainer=q_explainer,
                    localizer=localizer,
                    store=store,
                    audit=audit,
                    lang=lang,
                    phone=phone,
                    tree_id=chosen.id,
                )

        # 3b) No ready card: the router's decision (from step 1) picks the lane.
        route = analysis.route
        if route is Route.GREETING and case.active_tree is None:
            await store.save(case)
            await _audit(audit, case, OUTCOME_GREETING, ROUTE_GREETING)
            return _resp(case, _GREETING.get(lang, _GREETING["uz"]))
        if route is Route.RAG:
            reply = await _rag_answer(provider, grounding, interaction_log, case, message, lang)
            # A standalone question leaves no residue; a question mid-diagnosis
            # keeps the open case so the next message can still answer it.
            if case.active_tree is None:
                _start_fresh_case(case)
            if reply.requires_human:
                # No grounded answer: don't dead-end - offer the topics we can help
                # with so the user can pick one instead of only "contact a specialist".
                await store.save(case)
                await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_RAG)
                intro = _RAG_CLARIFY.get(lang, _RAG_CLARIFY["uz"])
                return await _menu(case, engine.trees(), intro, lang, localizer)
            await store.save(case)
            await _audit(audit, case, OUTCOME_ANSWER, ROUTE_RAG)
            return reply

        # 3c) CASE: enter the chosen tree, or clarify with a menu when none fits.
        if chosen is None and case.active_tree is None:
            # Only narrow the menu to one domain when the message clearly names it;
            # a vague "telefonim ishlamayapti" names neither, so offer both domains.
            menu_domain = route_domain or strong_domain(message)
            if menu_domain is not None and engine.trees_for_domain(menu_domain):
                by_lang = _DOMAIN_INTRO.get(lang, _DOMAIN_INTRO["uz"])
                intro = by_lang.get(menu_domain) or _ROUTE_INTRO.get(lang, _ROUTE_INTRO["uz"])
                await store.save(case)
                await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_CASE)
                return await _menu(
                    case, engine.trees_for_domain(menu_domain), intro, lang, localizer
                )
            await store.save(case)
            await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_CASE)
            return await _menu(
                case, engine.trees(), _ROUTE_INTRO.get(lang, _ROUTE_INTRO["uz"]), lang, localizer
            )
        if chosen is not None and chosen.id != case.active_tree:
            case.active_tree = chosen.id
            case.pending_node = chosen.root
            if case.domain is None:
                case.domain = chosen.domain
            _refresh_unknowns(case)

    # 4) Walk from the current node, skipping questions the facts already answer.
    active_tree = case.active_tree
    kind, obj = engine.advance(case.active_tree or "", case.pending_node or "", case.known_facts())
    if kind == "resolve" and isinstance(obj, ResolutionCard):
        return await _finalize_card(
            obj,
            case,
            engine=engine,
            orchestrator=orchestrator,
            explainer=explainer,
            q_explainer=q_explainer,
            localizer=localizer,
            store=store,
            audit=audit,
            lang=lang,
            phone=phone,
            tree_id=active_tree,
        )
    if kind == "ask" and isinstance(obj, DiagnosticNode):
        case.pending_node = obj.id
        case.status = CaseStatus.DIAGNOSING
        await store.save(case)
        await _audit(audit, case, OUTCOME_QUESTION, ROUTE_CASE, tree_id=active_tree)
        # Rephrase the question naturally; option values never change, but their
        # display labels are localized for scripts the tree has no native text for.
        question = await q_explainer.explain(obj.question.get(lang), case, lang)
        labels = await _localize_labels(localizer, [o.label.get(lang) for o in obj.options], lang)
        options = [
            OptionOut(value=o.value, label=label)
            for o, label in zip(obj.options, labels, strict=True)
        ]
        return _resp(case, question, options=options)

    case.status = CaseStatus.HANDOFF
    case.active_tree = None
    case.pending_node = None
    await store.save(case)
    await _audit(audit, case, OUTCOME_HANDOFF, ROUTE_CASE, tree_id=active_tree)
    return _resp(case, _HANDOFF_REPLY.get(lang, _HANDOFF_REPLY["uz"]), requires_human=True)


def _outcome_of(resp: ConverseCaseResponse) -> str:
    """Classify a response for the interaction log (mirrors the eval lanes)."""
    if resp.requires_human:
        return "handoff"  # includes a RAG abstention (done, but no grounded answer)
    if resp.done:
        return "resolved" if resp.card_id else "answer"
    values = [o.value for o in resp.options]
    if values and all("-" in value for value in values):
        return "menu"
    if values:
        return "question"
    return "greeting"


async def _log_interaction(
    request: Request, payload: ConverseCaseRequest, resp: ConverseCaseResponse
) -> None:
    """Capture the turn (message redacted) for offline analysis and improvement."""
    log = getattr(request.app.state, "interaction_log", None)
    if log is None:
        return
    await log.record(
        InteractionRecord(
            session_id=payload.session_id,
            channel=payload.channel,
            language=payload.language,
            message=redact_likely_pii(payload.message),
            reply=resp.reply,
            domain=resp.domain,
            outcome=_outcome_of(resp),
            card_id=resp.card_id,
            options=[o.value for o in resp.options],
            known_facts=resp.known_facts,
            sources=[s.doc_id for s in resp.sources],
            requires_human=resp.requires_human,
            done=resp.done,
        )
    )


@router.post("/converse", response_model=ConverseCaseResponse)
async def assistant_converse(
    payload: ConverseCaseRequest, request: Request
) -> ConverseCaseResponse:
    """One conversation turn, then capture it to the interaction log."""
    response = await _converse_turn(payload, request)
    await _log_interaction(request, payload, response)
    return response


_FEEDBACK_REPLY = {
    "uz": "Rahmat! Fikringiz xizmatni yaxshilashga yordam beradi.",
    "uz_cyrl": "Раҳмат! Фикрингиз хизматни яхшилашга ёрдам беради.",
    "ru": "Спасибо! Ваш отзыв поможет улучшить сервис.",
    "en": "Thank you! Your feedback helps us improve.",
    "kaa": "Raxmet! Pikirińiz xızmetti jaqsılawǵa járdem beredi.",
}


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    helpful: bool
    card_id: str | None = None
    language: str = Field(default="uz", pattern="^(uz|uz_cyrl|ru|en|kaa)$")
    channel: str = Field(default="web", pattern="^(web|telegram)$")


class FeedbackResponse(BaseModel):
    ok: bool
    reply: str


@router.post("/feedback", response_model=FeedbackResponse)
async def assistant_feedback(payload: FeedbackRequest, request: Request) -> FeedbackResponse:
    """Record whether a resolution actually solved the user's problem (CSAT)."""
    log = getattr(request.app.state, "interaction_log", None)
    if log is not None:
        await log.record(
            InteractionRecord(
                session_id=payload.session_id,
                channel=payload.channel,
                language=payload.language,
                kind="feedback",
                outcome="feedback",
                card_id=payload.card_id,
                feedback="helpful" if payload.helpful else "unhelpful",
            )
        )
    reply = _FEEDBACK_REPLY.get(payload.language, _FEEDBACK_REPLY["uz"])
    return FeedbackResponse(ok=True, reply=reply)


# --- /assistant/converse/stream: progressively render the validated reply ------

_WORD_CHUNK = re.compile(r"\s*\S+|\s+")


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/converse/stream")
async def assistant_converse_stream(
    payload: ConverseCaseRequest, request: Request
) -> StreamingResponse:
    """Stream the same reply as /converse, word by word (Server-Sent Events).

    The full turn - understanding, routing, grounding, PII redaction, abstention -
    runs first and is fully validated; only then is the finished reply text
    streamed for a natural typing effect, so no unvalidated text is ever shown.
    """
    response = await assistant_converse(payload, request)

    async def events() -> AsyncIterator[str]:
        for chunk in _WORD_CHUNK.findall(response.reply):
            yield _sse({"type": "delta", "text": chunk})
            await asyncio.sleep(0.012)
        meta = response.model_dump()
        meta.pop("reply", None)  # already streamed as deltas
        meta["type"] = "done"
        yield _sse(meta)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
