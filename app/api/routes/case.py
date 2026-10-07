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
from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.domain.case_state import CaseState, CaseStatus, ExplanationStyle, Fact, FactStatus, Outcome
from app.domain.diagnostics import DecisionTree, DiagnosticNode, ResolutionCard
from app.domain.enums import Category, Language
from app.domain.knowledge_gap import RetrievedDoc
from app.domain.legal_clauses import Clause
from app.domain.policy import PolicyRule
from app.domain.schemas import LLMRequest
from app.providers.base import LLMProvider
from app.providers.errors import ProviderError
from app.services.audit_log import (
    OUTCOME_ANSWER,
    OUTCOME_CALL_1170,
    OUTCOME_CLARIFY,
    OUTCOME_GREETING,
    OUTCOME_HANDOFF,
    OUTCOME_LC_FAILURE,
    OUTCOME_LC_PARTIAL,
    OUTCOME_LC_SUCCESS,
    OUTCOME_LC_UNCLEAR,
    OUTCOME_QUESTION,
    OUTCOME_RESOLVED,
    ROUTE_CASE,
    ROUTE_GREETING,
    ROUTE_POLICY,
    ROUTE_RAG,
    AuditEvent,
    AuditLog,
)
from app.services.card_answer import CardAnswerComposer
from app.services.card_explainer import CardExplainer
from app.services.case_store import CaseStore
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.explanation import detect_style, reexplain_leadin, style_for_confusion
from app.services.fact_extraction import (
    IMEI_FACT_FIELDS,
    MNP_FACT_FIELDS,
    FactExtractor,
    detect_domain,
    strong_domain,
)
from app.services.grounding import GroundingValidator
from app.services.intent_control import (
    FEE_ORIGIN_QUESTION,
    PAYMENT_RECEIPT,
    REGISTRATION_FEE,
    detect_intent,
    fee_followup_reply,
    fee_reply,
    mentions_amount,
    receipt_reply,
    transaction_facts,
)
from app.services.interaction_log import InteractionLog, InteractionRecord
from app.services.kb_retriever import get_retriever
from app.services.knowledge_gap import KnowledgeGapStore
from app.services.language_detect import detect_language
from app.services.learned_knowledge import LearnedKnowledgeStore
from app.services.legal_reasoning import LegalReasoningEngine
from app.services.localizer import Localizer
from app.services.meta_intent import (
    CORRECTION,
    NONE_OF_ABOVE,
    OTHER_ISSUE,
    RESTART,
    conversation_act,
    is_new_request,
    wants_reasoned_answer,
)
from app.services.outcome_analyzer import OutcomeAnalysis, OutcomeAnalyzer
from app.services.pii import redact_likely_pii
from app.services.policy_answer import PolicyAnswerComposer, build_policy_summary
from app.services.policy_matcher import PolicyMatch, PolicyMatcher
from app.services.question_explainer import QuestionExplainer
from app.services.resolution_orchestrator import (
    AWAITING_OUTCOME,
    CALL_1170_REQUESTED,
    OrchestratorDecision,
    ResolutionOrchestrator,
)
from app.services.response_quality import CAPABILITY_CLAIM, check_reply
from app.services.router import Route
from app.services.status_capability import (
    SEED_ENTRY_BY_KIND,
    claims_live_check,
    detect_status_request,
    reported_status_reply,
    status_request_reply,
)
from app.services.tree_coverage import TreeCoverageEvaluator
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
    "en": {
        "imei": "What exactly do you need help with on IMEI?",
        "mnp": "What exactly do you need help with on MNP?",
    },
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
# §22 RAG applicability: a retrieved passage much weaker than the best hit is almost
# always a different topic riding along on one shared word (a receipt question pulling
# in a registration-fee article). Retrieved does not mean applicable, so only the best
# hit and passages within this fraction of its score drive the grounded answer.
_RAG_APPLICABILITY_RATIO = 0.5
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
    style: str | None = None,
    detail: str | None = None,
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
            style=style,
            detail=detail,
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
    case.awaiting_menu = False
    case.current_intent = None
    case.current_problem = None
    case.conversation_summary = None
    # original_problem is intentionally NOT cleared here: the RAG lane resets the
    # diagnostic slate between turns, but a menu shown next must still re-examine the
    # original problem. It is cleared only when a genuinely new problem begins.


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


def _card_body(card: ResolutionCard, cause: str, lang: str) -> str:
    """The deterministic approved resolution: cause, then the exact steps, documents,
    place to apply, link and contact. This is the ground truth the composer must
    preserve - and the fallback whenever the LLM composition is unavailable."""
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


async def _card_reply(
    explainer: CardExplainer,
    composer: CardAnswerComposer,
    card: ResolutionCard,
    case: CaseState,
    lang: str,
) -> str:
    """Compose the final answer from the approved card used as evidence.

    The deterministic body (LLM-explained cause plus the exact approved steps,
    documents, place, link and contact) is built first; the composer then turns it
    into one natural, situation-aware message, but only when every fact is preserved
    - otherwise that exact body is returned. So the wording is never a fixed form,
    yet the engine and knowledge base still own every fee, deadline, link and number.
    """
    cause = await explainer.explain(card.probable_cause.get(lang), case, lang)
    body = _card_body(card, cause, lang)
    return await composer.compose(card, case, lang, body)


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
# Shown when a specific issue is covered by neither a tree nor the knowledge base:
# never guess, never fall into a generic tree root - say so and recommend 1170.
_UNSUPPORTED_1170 = {
    "uz": "Bu savol bo'yicha tasdiqlangan bilim bazamda aniq yechim topilmadi. "
    "Noto'g'ri yo'l ko'rsatmaslik uchun {phone} raqamiga qo'ng'iroq qiling.",
    "uz_cyrl": "Бу савол бўйича тасдиқланган билим базамда аниқ ечим топилмади. "
    "Нотўғри йўл кўрсатмаслик учун {phone} рақамига қўнғироқ қилинг.",
    "ru": "По этому вопросу в проверенной базе знаний нет точного решения. "
    "Чтобы не дать неверный совет, позвоните по номеру {phone}.",
    "en": "I don't have a confirmed answer for this in the knowledge base. "
    "To avoid giving wrong guidance, please call {phone}.",
    "kaa": "Bul soraw boyınsha tastıyıqlanǵan bilim bazamda anıq sheshim tabılmadı. "
    "Qáte baǵdar bermew ushın {phone} nomerine qońıraw etiń.",
}
# Shown after the customer rejects the offered menu and the knowledge base still has
# no grounded answer for the original problem: acknowledge, then recommend 1170.
_MENU_REJECTED_1170 = {
    "uz": "Taklif qilingan variantlar sizning holatingizga mos kelmaganini tushundim. "
    "Tasdiqlangan bilim bazamda bu holat bo'yicha aniq yechim topilmadi. "
    "Noto'g'ri yo'l ko'rsatmaslik uchun {phone} raqamiga qo'ng'iroq qiling.",
    "uz_cyrl": "Таклиф қилинган вариантлар сизнинг ҳолатингизга мос келмаганини тушундим. "
    "Тасдиқланган билим базамда бу ҳолат бўйича аниқ ечим топилмади. "
    "Нотўғри йўл кўрсатмаслик учун {phone} рақамига қўнғироқ қилинг.",
    "ru": "Понял, что предложенные варианты вам не подходят. В проверенной базе знаний "
    "нет точного решения для этого случая. Чтобы не дать неверный совет, "
    "позвоните по номеру {phone}.",
    "en": "I understand none of the offered options fit your case. I don't have a "
    "confirmed answer for this in the knowledge base. To avoid wrong guidance, "
    "please call {phone}.",
    "kaa": "Usınılǵan variantlar sizge sáykes kelmegenin túsindim. Tastıyıqlanǵan bilim "
    "bazamda bul jaǵday boyınsha anıq sheshim joq. Qáte baǵdar bermew ushın "
    "{phone} nomerine qońıraw etiń.",
}
_OTHER_ISSUE_PROMPT = {
    "uz": "Tushundim, boshqa muammo. Uni o'z so'zingiz bilan yozing.",
    "uz_cyrl": "Тушундим, бошқа муаммо. Уни ўз сўзингиз билан ёзинг.",
    "ru": "Понял, другая проблема. Опишите её своими словами.",
    "en": "Understood, a different problem. Describe it in your own words.",
    "kaa": "Túsindim, basqa másele. Onı óz sózińiz benen jazıń.",
}
_CORRECTION_PROMPT = {
    "uz": "Kechirasiz, noto'g'ri tushundim. Muammoni o'z so'zingiz bilan qisqa qaytaring.",
    "uz_cyrl": "Кечирасиз, нотўғри тушундим. Муаммони ўз сўзингиз билан қисқа қайтаринг.",
    "ru": "Извините, я понял неверно. Опишите проблему своими словами ещё раз, коротко.",
    "en": "Sorry, I misunderstood. Please restate the problem in your own words, briefly.",
    "kaa": "Keshiriń, qáte túsindim. Máseleni óz sózińiz benen qısqa qaytalań.",
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
    explainer: CardExplainer,
    composer: CardAnswerComposer,
    card: ResolutionCard,
    case: CaseState,
    lang: str,
) -> str:
    """The card's full resolution text followed by its success-check question."""
    body = await _card_reply(explainer, composer, card, case, lang)
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


def _applicable_results(results: list[Any]) -> list[Any]:
    """Keep only passages applicable to the query (spec §22).

    Results arrive sorted by score. The best hit is always kept; a passage scoring
    far below it is treated as a different topic that merely shares a word, and is
    dropped so an irrelevant article never drives the grounded answer.
    """
    if not results:
        return results
    floor = results[0].score * _RAG_APPLICABILITY_RATIO
    return [r for r in results if r.score >= floor]


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


# The legal-basis footer: a clause citation (not a canned answer) appended to a
# policy-grounded tree resolution, so the customer sees which law it rests on.
_LEGAL_BASIS = {
    "uz": "⚖️ Huquqiy asos: VMQ-778 — {clauses}. To'liq matn: {url}",
    "uz_cyrl": "⚖️ Ҳуқуқий асос: ВМҚ-778 — {clauses}. Тўлиқ матн: {url}",
    "ru": "⚖️ Правовая основа: ВМК-778 — {clauses}. Полный текст: {url}",
    "en": "⚖️ Legal basis: Reg. 778 — {clauses}. Full text: {url}",
    "kaa": "⚖️ Nızamlıq tiykarı: VMQ-778 — {clauses}. Tolıq matn: {url}",
}
_SUPERSCRIPT = {"1": "¹", "2": "²", "3": "³"}


def _fmt_clause(clause: str) -> str:
    """Render a clause label: "6" -> "6-band", "6-1" -> "6¹-band", "6-ilova" kept."""
    if clause.endswith("ilova"):
        return clause
    base, _, sub = clause.partition("-")
    if sub and sub.isdigit():
        return base + "".join(_SUPERSCRIPT.get(d, d) for d in sub) + "-band"
    return f"{clause}-band"


def _distinct_clauses(rules: list[PolicyRule]) -> list[str]:
    seen: list[str] = []
    for rule in rules:
        if rule.clause not in seen:
            seen.append(rule.clause)
    return seen


def _legal_footer(rules: list[PolicyRule], lang: str) -> str:
    """A concise clause-and-source citation for the rules a card is grounded in."""
    if not rules:
        return ""
    clauses = ", ".join(_fmt_clause(c) for c in _distinct_clauses(rules))
    template = _LEGAL_BASIS.get(lang, _LEGAL_BASIS["uz"])
    return template.format(clauses=clauses, url=rules[0].source_url)


def _policy_sources(rules: list[PolicyRule]) -> list[SourceOut]:
    """Clause-level sources for the trace: one per distinct clause, titled by clause.

    Titling each by its clause (not a bare "VMQ-778" repeated) keeps the sources list
    informative instead of showing the same document name many times. Capped to the
    few leading clauses so the citation stays readable.
    """
    document = rules[0].document if rules else "VMQ-778"
    cited = f"{document} ({', '.join(_fmt_clause(c) for c in _distinct_clauses(rules)[:5])})"
    return [SourceOut(doc_id=cited, title=cited)]


def _clause_to_rule(clause: Clause) -> PolicyRule:
    """Adapt a full-base Clause into a PolicyRule so the composer can cite it.

    Carries the clause's paraphrased meaning, number and source; it holds no
    applies_if/actions of its own (those live on the curated situation rules), it is
    added purely to widen the legal basis of the answer from the whole regulation.
    """
    return PolicyRule(
        rule_id=clause.rule_id,
        document=clause.source,
        clause=clause.clause,
        effective_from=date(2019, 9, 17),
        topic=clause.subject,
        legal_rule=clause.legal_rule,
        payment_ref=clause.payment_ref,
        source_url=clause.source_url,
    )


async def _maybe_policy_answer(
    engine: LegalReasoningEngine,
    composer: PolicyAnswerComposer,
    case: CaseState,
    message: str,
    lang: str,
    store: CaseStore,
    audit: AuditLog,
    *,
    require_trigger: bool = True,
) -> ConverseCaseResponse | None:
    """Answer a standalone legal question with the Legal Reasoning Engine, or None.

    The engine reasons over the WHOLE VMQ-778 base: it derives the situation, retrieves
    the relevant clauses by meaning, applies the specific over the general, and resolves
    any payment. Engagement stays conservative - a real situation signal plus a
    situation-specific curated rule - so off-topic or bare questions still fall through
    to the knowledge base / 1170. The curated situation rules (with their steps and
    documents) plus the retrieved clauses form the legal basis; the composer writes the
    natural answer and a legal-grounding check confirms every cited clause is from it.
    """
    query_vector = await engine.embed(message)  # semantic recall when configured, else None
    reasoning = engine.reason(case, message, query_vector=query_vector)
    if not reasoning.has_grounds():
        return None
    # Conservative engagement for the RAG / no-coverage lanes: require a real situation
    # signal and a situation-specific rule, so an off-topic or bare question falls
    # through. The caller lifts this (require_trigger=False) when it already knows the
    # message wants a reasoned answer - a permission question or an admin-action request
    # - where grounds alone are enough and there may be no device-origin signal.
    if require_trigger:
        trigger = set(reasoning.case_facts.signals) - {"user_is_resident"}
        specific = [
            rule
            for rule in reasoning.situation_rules
            if rule.specificity() >= 1 and rule.applies_if != ["user_is_resident"]
        ]
        if not trigger or not specific:
            return None

    # Legal basis: the curated situation rules first (they carry steps/documents),
    # then the clauses the engine retrieved from the whole law, de-duplicated.
    rules: list[PolicyRule] = list(reasoning.situation_rules)
    have = {rule.clause for rule in rules}
    # Keep the basis focused: the curated rules plus the most relevant few clauses.
    for label in reasoning.legal_basis[:5]:
        clause = engine.clause(label)
        if clause is not None and clause.clause not in have:
            rules.append(_clause_to_rule(clause))
            have.add(clause.clause)

    match = PolicyMatch(rules=rules, signals=set(reasoning.case_facts.signals))
    payments = reasoning.payments
    summary = build_policy_summary(match, payments, lang, rules[0].source_url)
    text = await composer.compose(match, payments, lang, message, summary)
    sources = _policy_sources(rules)
    _start_fresh_case(case)
    case.domain = case.domain or "imei"
    case.status = CaseStatus.RESOLVED
    await store.save(case)
    detail = "policy:" + ",".join(reasoning.legal_basis[:5])
    await _audit(audit, case, OUTCOME_ANSWER, ROUTE_POLICY, detail=detail)
    return _resp(case, text, done=True, sources=sources)


async def _rag_answer(
    provider: LLMProvider,
    grounding: GroundingValidator,
    log: InteractionLog | None,
    case: CaseState,
    message: str,
    lang: str,
    gaps: KnowledgeGapStore | None = None,
    learned: LearnedKnowledgeStore | None = None,
) -> ConverseCaseResponse:
    """Answer an informational question strictly from approved KB evidence.

    Expert-approved LEARNED knowledge is consulted first: if a published article
    (from the gap->expert->approval workflow) matches, its verified solution answers
    the question. Otherwise the static KB is retrieved and the provider answers only
    from it. It abstains - never invents an answer - when there is no evidence, the
    top hit is too weak, the provider fails, or the answer cites a source it was not
    given (grounding check). A KB gap (no/weak evidence or an ungroundable answer) is
    recorded as an 'unanswered' question AND as a structured knowledge gap so an
    expert can later supply the missing knowledge. Sources are returned only when it
    actually answers.
    """
    if learned is not None:
        hit = await learned.search(message)
        if hit is not None:
            source = SourceOut(doc_id=hit.article.article_id, title=hit.article.content.title)
            return _resp(case, hit.article.content.solution, done=True, sources=[source])
    retriever = get_retriever()
    results = retriever.retrieve(message, _RAG_TOP_K, domain=case.domain)
    docs = [RetrievedDoc(doc_id=r.chunk.doc_id, score=float(r.score)) for r in results]
    fallback = _NO_EVIDENCE_REPLY.get(lang, _NO_EVIDENCE_REPLY["uz"])
    # Abstain when there is no evidence or the best hit is too weak to trust.
    if not _has_strong_evidence(results, _RAG_MIN_SCORE):
        await _log_unanswered(log, case, message)
        await _record_gap(
            gaps, case, message, "no_evidence" if not results else "weak_evidence", docs
        )
        return _resp(case, fallback, done=True, requires_human=True)
    # §22: a retrieved article is not necessarily applicable; keep only passages close
    # to the best hit so an off-topic one does not steer the answer.
    results = _applicable_results(results)
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
        await _record_gap(gaps, case, message, "ungroundable", docs)
        return _resp(case, fallback, done=True, requires_human=True)
    # Capability rule: an answer must never claim a live-system lookup it cannot make.
    if claims_live_check(result.text):
        return _resp(case, fallback, done=True, requires_human=True)
    sources = [SourceOut(doc_id=r.chunk.doc_id, title=r.chunk.title) for r in results]
    return _resp(case, result.text, done=True, sources=sources)


async def _record_gap(
    gaps: KnowledgeGapStore | None,
    case: CaseState,
    message: str,
    reason: str,
    docs: list[RetrievedDoc] | None = None,
) -> None:
    """Record a structured knowledge gap at an abstention; best-effort, never raises."""
    if gaps is None:
        return
    try:
        await gaps.record(
            question=message,
            domain=case.domain,
            intent=case.user_goal or case.problem_summary,
            reason=reason,
            conversation_context=case.problem_summary or case.original_problem,
            retrieval_queries=[message],
            retrieved_documents=docs or [],
            case_id=case.case_id,
        )
    except Exception:  # pragma: no cover - gap capture must never break a turn
        return


async def _render_decision(
    decision: OrchestratorDecision,
    case: CaseState,
    *,
    engine: DiagnosticEngine,
    explainer: CardExplainer,
    composer: CardAnswerComposer,
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
    if decision.kind == "reexplain" and decision.card is not None:
        # Don't repeat the same words: escalate the style and lead with a fresh line.
        case.explanation.style = style_for_confusion(case.explanation.confusion_count)
        leadin = reexplain_leadin(case.explanation.style, lang)
        body = await _offer_reply(explainer, composer, decision.card, case, lang)
        return _resp(
            case,
            f"{leadin}\n\n{body}",
            options=_result_options(lang),
            card_id=decision.card.id,
            done=False,
        )
    if decision.kind == "offer_card" and decision.card is not None:
        reply = await _offer_reply(explainer, composer, decision.card, case, lang)
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


_LIFECYCLE_OUTCOME_LABELS = {
    Outcome.SUCCESS: OUTCOME_LC_SUCCESS,
    Outcome.FAILURE: OUTCOME_LC_FAILURE,
    Outcome.PARTIAL: OUTCOME_LC_PARTIAL,
    Outcome.UNCLEAR: OUTCOME_LC_UNCLEAR,
}


def _lifecycle_outcome_label(decision: OrchestratorDecision, result: Outcome | None) -> str:
    """Audit label for a lifecycle turn: the classified result, or the 1170 fallback."""
    if decision.kind == "call_1170":
        return OUTCOME_CALL_1170
    if result is not None:
        return _LIFECYCLE_OUTCOME_LABELS[result]
    return OUTCOME_QUESTION


def _apply_style_cue(case: CaseState, message: str, lang: str) -> None:
    """Adapt how the customer is addressed from their words (facts never change)."""
    case.explanation.language = lang
    style = detect_style(message)
    if style is not None:
        case.explanation.style = style
        if style is ExplanationStyle.EXAMPLE:
            case.explanation.needs_examples = True


def _attach_legal_basis(
    resp: ConverseCaseResponse, rules: list[PolicyRule], lang: str
) -> ConverseCaseResponse:
    """Append the clause-and-source citation and add the clause-level sources.

    Binds a tree resolution to the law the customer can see: a short legal-basis line
    and one source per cited clause. The answer body stays LLM-composed; this only
    adds the citation the spec asks for ("band va manbani ko'rsatish").
    """
    footer = _legal_footer(rules, lang)
    if not footer:
        return resp
    sources = (resp.sources or []) + _policy_sources(rules)
    return resp.model_copy(update={"reply": f"{resp.reply}\n\n{footer}", "sources": sources})


async def _finalize_card(
    card: ResolutionCard,
    case: CaseState,
    *,
    engine: DiagnosticEngine,
    orchestrator: ResolutionOrchestrator,
    explainer: CardExplainer,
    composer: CardAnswerComposer,
    q_explainer: QuestionExplainer,
    localizer: Localizer,
    store: CaseStore,
    audit: AuditLog,
    lang: str,
    phone: str,
    tree_id: str | None = None,
    policy_rules: list[PolicyRule] | None = None,
) -> ConverseCaseResponse:
    """Offer a reached card through the lifecycle, or close it as a one-shot answer.

    A card with a success_check enters the result-tracking loop (offered, then its
    result awaited); any other card keeps the previous behaviour: closed at once.
    The card's grounding rules (``policy_rules``) are cited on the resolution shown
    and recorded in the audit trail, so every outcome is tied to the law.
    """
    rules = policy_rules or []
    detail = ("policy:" + ",".join(r.rule_id for r in rules)) if rules else None
    if orchestrator.uses_lifecycle(card):
        if tree_id and case.active_tree is None:
            case.active_tree = tree_id  # keep the tree so alternatives can be found
        decision = orchestrator.offer_card(case, card)
        await store.save(case)
        await _audit(
            audit,
            case,
            OUTCOME_QUESTION,
            ROUTE_CASE,
            card_id=card.id,
            tree_id=tree_id,
            detail=detail,
        )
        resp = await _render_decision(
            decision,
            case,
            engine=engine,
            explainer=explainer,
            composer=composer,
            q_explainer=q_explainer,
            localizer=localizer,
            lang=lang,
            phone=phone,
        )
        # Cite the legal basis only on the offered resolution itself.
        return _attach_legal_basis(resp, rules, lang) if resp.card_id == card.id else resp
    case.active_tree = None
    case.pending_node = None
    case.resolution_card_id = card.id
    case.status = CaseStatus.RESOLVED
    await store.save(case)
    await _audit(
        audit, case, OUTCOME_RESOLVED, ROUTE_CASE, card_id=card.id, tree_id=tree_id, detail=detail
    )
    card_text = await _card_reply(explainer, composer, card, case, lang)
    return _attach_legal_basis(_resp(case, card_text, done=True, card_id=card.id), rules, lang)


async def _intent_answer(
    case: CaseState, message: str, lang: str, gaps: KnowledgeGapStore | None
) -> ConverseCaseResponse | None:
    """Answer the customer's current explicit goal, or None to route normally.

    The goal is the one THIS conversation step is about (``case.current_intent``,
    set from the current message). A receipt request is answered at once - the
    capability limit, then what the customer can do - and, because the knowledge
    base has no receipt-retrieval procedure, recorded as a knowledge gap instead of
    inventing one. A fee complaint asks one question only when where the phone came
    from is still unknown; that question is never asked twice.
    """
    known = case.known_facts()
    if case.current_intent == PAYMENT_RECEIPT:
        case.user_goal = PAYMENT_RECEIPT
        case.last_question = None
        await _record_gap(gaps, case, message, "no_coverage")
        case.status = CaseStatus.RESOLVED
        succeeded = known.get("registration_status") == "success"
        return _resp(case, receipt_reply(lang, registration_succeeded=succeeded), done=True)
    if case.current_intent != REGISTRATION_FEE:
        return None
    origin = known.get("device_origin")
    if case.last_question == FEE_ORIGIN_QUESTION:
        # This message should answer the one question asked. If it did not (or it is
        # a new problem), the fee flow ends here - the question is never repeated.
        case.last_question = None
        if origin is None or is_new_request(message):
            case.current_intent = None
            return None
        case.status = CaseStatus.RESOLVED
        return _resp(case, fee_followup_reply(lang, origin), done=True)
    if detect_intent(message) != REGISTRATION_FEE:
        case.current_intent = None  # an earlier turn's goal is never carried over
        return None
    reply = fee_reply(lang, amount_quoted=mentions_amount(message), device_origin=origin)
    if origin is None:
        case.last_question = FEE_ORIGIN_QUESTION
        return _resp(case, reply)  # one question, free-text answer, no menu
    case.status = CaseStatus.RESOLVED
    return _resp(case, reply, done=True)


async def _converse_turn(payload: ConverseCaseRequest, request: Request) -> ConverseCaseResponse:
    """One conversation turn: greet, route, extract facts, ask only what's missing."""
    store = cast(CaseStore, request.app.state.case_store)
    analyzer = cast(TurnAnalyzer, request.app.state.turn_analyzer)
    engine = cast(DiagnosticEngine, request.app.state.diagnostic_engine)
    provider = cast(LLMProvider, request.app.state.provider)
    explainer = cast(CardExplainer, request.app.state.card_explainer)
    composer = cast(CardAnswerComposer, request.app.state.card_answer)
    q_explainer = cast(QuestionExplainer, request.app.state.question_explainer)
    localizer = cast(Localizer, request.app.state.localizer)
    grounding = cast(GroundingValidator, request.app.state.grounding)
    audit = cast(AuditLog, request.app.state.audit_log)
    interaction_log = cast(InteractionLog, getattr(request.app.state, "interaction_log", None))
    knowledge_gaps = cast(
        "KnowledgeGapStore | None", getattr(request.app.state, "knowledge_gaps", None)
    )
    learned_knowledge = cast(
        "LearnedKnowledgeStore | None", getattr(request.app.state, "learned_knowledge", None)
    )
    orchestrator = cast(ResolutionOrchestrator, request.app.state.resolution_orchestrator)
    outcome_analyzer = cast(OutcomeAnalyzer, request.app.state.outcome_analyzer)
    coverage_eval = cast(TreeCoverageEvaluator, request.app.state.tree_coverage)
    policy_matcher = cast(PolicyMatcher, request.app.state.policy_matcher)
    policy_composer = cast(PolicyAnswerComposer, request.app.state.policy_answer)
    reasoning_engine = cast(LegalReasoningEngine, request.app.state.legal_reasoning)
    phone = str(
        getattr(getattr(request.app.state, "settings", None), "approved_support_phone", None)
        or "1170"
    )

    case = await store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1
    # Redact PII up front: nothing raw reaches the LLM, the KB, the persisted case
    # or the logs. Only labelled/structured identifiers are redacted, so tariffs
    # and short official numbers pass through untouched.
    message = redact_likely_pii(payload.message)
    # Reply in the language the customer actually wrote: weigh the message and switch
    # only on a clear lead, keeping the incoming language for a short/ambiguous message
    # (a button value, a terse reply) so the language never flips on thin evidence.
    lang = detect_language(message, default=payload.language)
    # Adapt the explanation style to the customer's words before anything else, so a
    # "explain simply" or "give an example" takes effect on this very turn.
    _apply_style_cue(case, message, lang)
    # Whether a menu was awaiting a choice on the PREVIOUS turn (so a rejection like
    # "muammom ro'yxatda yo'q" is read as rejecting it, not as a new problem). Reset
    # now; a menu shown this turn sets it again before returning.
    was_awaiting_menu = case.awaiting_menu
    case.awaiting_menu = False

    # A previously closed case starts fresh so old facts don't auto-complete a new one.
    if case.status in (CaseStatus.RESOLVED, CaseStatus.HANDOFF, CaseStatus.CALL_1170_RECOMMENDED):
        _start_fresh_case(case)
        case.original_problem = None  # a genuinely new problem follows

    # 0-intent) What is the customer's goal NOW? An explicit request in this message
    #   outranks everything from earlier turns: when it names a different goal than
    #   the one being worked on (a fee complaint becomes "I paid, I need the receipt"),
    #   the old diagnostic flow, open question, menu or awaited result is dropped so
    #   it is never continued against the new request.
    intent = detect_intent(message)
    if intent is not None and intent != case.current_intent:
        if case.active_tree or case.pending_node or case.resolution_card_id or was_awaiting_menu:
            _start_fresh_case(case)
            case.original_problem = None
            was_awaiting_menu = False
        case.current_intent = intent
        case.current_problem = message

    # 0) A case awaiting a result: this message is normally the outcome of the offered
    #    card. But a pending question must never swallow a new, self-contained request:
    #    if the message is a new complete question (e.g. a standalone pricing question
    #    while we await an error text), supersede the awaited card and re-plan from
    #    scratch instead of treating it as the card's result.
    if (
        case.status in AWAITING_OUTCOME
        and case.resolution_card_id
        and _result_from_value(payload.message.strip()) is None
        and not _wants_phone(message)
        and is_new_request(message)
    ):
        _start_fresh_case(case)
        case.original_problem = None  # the new request becomes the new problem
    elif case.status in AWAITING_OUTCOME and case.resolution_card_id:
        case.last_customer_reply = message
        card = engine.get_card(case.resolution_card_id)
        forced = _result_from_value(payload.message.strip())
        result_outcome: Outcome | None = None
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
            result_outcome = outcome.outcome
            decision = orchestrator.advance(case, outcome)
        await store.save(case)
        await _audit(
            audit,
            case,
            _lifecycle_outcome_label(decision, result_outcome),
            ROUTE_CASE,
            card_id=card.id if card else None,
            style=case.explanation.style.value,
            detail=case.call_1170_reason if decision.kind == "call_1170" else None,
        )
        return await _render_decision(
            decision,
            case,
            engine=engine,
            explainer=explainer,
            composer=composer,
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
    # A completed step the customer reports (registration succeeded, payment made,
    # receipt missing) is a fact to respect - it is never diagnosed as a failure.
    for fact in transaction_facts(message, turn_id=case.turn_count):
        case.upsert(fact)
    if case.domain is None:
        # The analyzer's domain understands typos/dialect; keyword detection is the net.
        case.domain = analysis.domain or detect_domain(message)
    _refresh_unknowns(case)
    # Keep the first real problem so a later menu rejection re-examines it, not the
    # rejection text (whose "ro'yxatda" would otherwise look like a registration intent).
    if case.original_problem is None and analysis.route is not Route.GREETING:
        case.original_problem = message

    # 1-meta) A conversation act ABOUT the dialogue (restart / correction / menu
    #   rejection / other problem) is handled before the message is read as a tree
    #   answer or routed by keyword, so a menu rejection never enters a tree root.
    act = conversation_act(message)
    pending = was_awaiting_menu or (case.active_tree is not None and case.pending_node is not None)
    if act == RESTART:
        _start_fresh_case(case)
        case.original_problem = None
        await store.save(case)
        await _audit(audit, case, OUTCOME_GREETING, ROUTE_GREETING, detail="restart")
        return _resp(case, _GREETING.get(lang, _GREETING["uz"]))
    if act == OTHER_ISSUE:
        _start_fresh_case(case)  # a genuinely new problem; the old one is forgotten
        case.original_problem = None
        await store.save(case)
        await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_CASE, detail="other_issue")
        return _resp(case, _OTHER_ISSUE_PROMPT.get(lang, _OTHER_ISSUE_PROMPT["uz"]))
    if pending and act == CORRECTION:
        case.active_tree = None
        case.pending_node = None
        await store.save(case)
        await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_CASE, detail="correction")
        return _resp(case, _CORRECTION_PROMPT.get(lang, _CORRECTION_PROMPT["uz"]))
    if pending and act == NONE_OF_ABOVE:
        # The menu did not fit. Re-examine the ORIGINAL problem from the knowledge
        # base - never the rejection text, never a generic tree root.
        case.active_tree = None
        case.pending_node = None
        original = case.original_problem or message
        reply = await _rag_answer(
            provider,
            grounding,
            interaction_log,
            case,
            original,
            lang,
            knowledge_gaps,
            learned_knowledge,
        )
        if not reply.requires_human:
            await store.save(case)
            await _audit(audit, case, OUTCOME_ANSWER, ROUTE_RAG, detail="none_of_above")
            return reply
        case.status = CaseStatus.CALL_1170_RECOMMENDED
        case.call_1170_reason = "menu_rejected_no_coverage"
        await store.save(case)
        await _audit(audit, case, OUTCOME_CALL_1170, ROUTE_CASE, detail="menu_rejected_no_coverage")
        text = _MENU_REJECTED_1170.get(lang, _MENU_REJECTED_1170["uz"]).format(phone=phone)
        return _resp(case, text, done=True, requires_human=True, call_1170=True, phone=phone)

    # 1-status) Live-system status (knowledge base capability rule). The assistant has
    #   no UZIMEI/MNP/customs/operator integration, so it never FINDS a status: an
    #   official status code the customer pasted is explained from its seed entry,
    #   and a request to look one up is answered honestly ("I can't check this
    #   directly") with what to send next - never a dead end and never a pretend
    #   lookup (it names the official way to check instead). Both run before a
    #   pending tree question can mistake them for answers, and leave the case open
    #   so the customer's next message continues it.
    reported = reported_status_reply(message, lang)
    if reported is not None:
        # KB rule 5: the status the customer reported is a first-class fact; it is
        # never replaced by one the assistant guessed.
        case.upsert(
            Fact(
                name="user_reported_status",
                value=reported.code,
                status=FactStatus.EXPLICIT,
                turn_id=case.turn_count,
            )
        )
        await store.save(case)
        await _audit(
            audit,
            case,
            OUTCOME_ANSWER,
            ROUTE_CASE,
            detail=f"reported_status:{reported.code}:{reported.seed_entry_id}",
        )
        return _resp(case, reported.reply)
    status_kind = detect_status_request(message)
    if status_kind is not None:
        await store.save(case)
        await _audit(
            audit,
            case,
            OUTCOME_CLARIFY,
            ROUTE_CASE,
            detail=f"status_lookup_unsupported:{status_kind}:{SEED_ENTRY_BY_KIND[status_kind]}",
        )
        return _resp(case, status_request_reply(status_kind, lang))

    # 1-intent) Answer the customer's explicit goal directly - no decision tree, no
    #   menu, and no question unless its answer changes the next step.
    intent_reply = await _intent_answer(case, message, lang, knowledge_gaps)
    if intent_reply is not None:
        await store.save(case)
        await _audit(
            audit,
            case,
            OUTCOME_ANSWER if intent_reply.done else OUTCOME_QUESTION,
            ROUTE_CASE,
            detail=f"intent:{case.current_intent}",
        )
        return intent_reply

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
                    composer=composer,
                    q_explainer=q_explainer,
                    localizer=localizer,
                    store=store,
                    audit=audit,
                    lang=lang,
                    phone=phone,
                    tree_id=case.active_tree,
                    policy_rules=policy_matcher.rules_for_ids(
                        resolved.policy_rule_ids, case, message
                    ),
                )
            answered = True

    # 3) Not an answer to an open question: pick the lane for this message.
    if not answered:
        # 3-pre) Expert-approved LEARNED knowledge comes first: a published article
        #    (from the gap -> expert -> approval loop) that STRONGLY matches a fresh
        #    question answers it before any tree/KB routing - this is how newly taught
        #    knowledge reaches users. The high score floor means only a clearly-matching
        #    article pre-empts; a generic problem still goes to its diagnostic tree.
        if case.active_tree is None and learned_knowledge is not None:
            hit = await learned_knowledge.strong_match(message)
            if hit is not None:
                _start_fresh_case(case)
                case.domain = case.domain or hit.article.content.domain
                case.status = CaseStatus.RESOLVED
                await store.save(case)
                await _audit(audit, case, OUTCOME_ANSWER, ROUTE_RAG, detail="learned_knowledge")
                src = [SourceOut(doc_id=hit.article.article_id, title=hit.article.content.title)]
                return _resp(case, hit.article.content.solution, done=True, sources=src)

        # 3) Coverage gate (applies to EVERY tree): the decision tree is one evaluated
        #    candidate, not a forced route. A message enters a tree only when a tree
        #    DIRECTLY covers it; a specific sub-issue no tree covers goes to the
        #    knowledge base, then 1170 - never a generic tree root.
        coverage = coverage_eval.evaluate(
            message, domain=case.domain, known_facts=case.known_facts()
        )
        if coverage.level == "none" and case.active_tree is None:
            # The law first: when a VMQ-778 rule fits the situation, answer from it
            # (natural, clause-cited) before the generic KB / 1170 fallback.
            policy_reply = await _maybe_policy_answer(
                reasoning_engine, policy_composer, case, message, lang, store, audit
            )
            if policy_reply is not None:
                return policy_reply
            reply = await _rag_answer(
                provider,
                grounding,
                interaction_log,
                case,
                message,
                lang,
                knowledge_gaps,
                learned_knowledge,
            )
            _start_fresh_case(case)
            if not reply.requires_human:
                await store.save(case)
                await _audit(audit, case, OUTCOME_ANSWER, ROUTE_RAG, detail=coverage.reason)
                return reply
            case.status = CaseStatus.CALL_1170_RECOMMENDED
            case.call_1170_reason = f"no_coverage:{coverage.issue}"
            await store.save(case)
            await _audit(
                audit, case, OUTCOME_CALL_1170, ROUTE_CASE, detail=f"no_coverage:{coverage.issue}"
            )
            text = _UNSUPPORTED_1170.get(lang, _UNSUPPORTED_1170["uz"]).format(phone=phone)
            return _resp(case, text, done=True, requires_human=True, call_1170=True, phone=phone)

        # Only a direct-coverage tree (or an explicit menu pick) may be entered; a
        # covered specific issue bypasses the greeting/RAG lanes, a keyword match does
        # not (so an informational question is still answered from the KB).
        route_domain = coverage.domain_hint
        chosen = engine.get_tree(message.strip()) or coverage.tree
        # The model's understanding, not just keywords, may select the tree: when it
        # reads the message as a concrete problem in a known domain but the wording
        # (typos, paraphrase) matched no tree's keywords, enter that domain's
        # diagnostic tree rather than dead-ending at a topic menu. The gate is a
        # concrete issue fact extracted from THIS message (e.g. registration_status) -
        # a vague domain mention ("imei tushunmayapman") extracts none and still gets
        # the topic menu. A decision fact pins the exact tree; else the domain's entry
        # tree, from whose root the diagnosis still proceeds fact by fact.
        if (
            chosen is None
            and case.active_tree is None
            and analysis.route is Route.CASE
            and analysis.facts
        ):
            inferred_domain = analysis.domain or route_domain
            if inferred_domain is not None:
                chosen = engine.tree_from_facts(
                    case.known_facts(), domain=inferred_domain
                ) or engine.primary_tree_for_domain(inferred_domain)

        # 3a-pre) A permission question ("...bo'ladimi?") or an administrative request
        #     (cancel/correct/re-submit an application) wants a reasoned legal answer,
        #     not a diagnostic walk - so the engine answers it from the law even when a
        #     tree's keywords matched. Only when not already mid-tree and the engine
        #     actually has grounds; otherwise fall through to the tree.
        if case.active_tree is None and wants_reasoned_answer(message):
            policy_reply = await _maybe_policy_answer(
                reasoning_engine,
                policy_composer,
                case,
                message,
                lang,
                store,
                audit,
                require_trigger=False,
            )
            if policy_reply is not None:
                return policy_reply

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
                    composer=composer,
                    q_explainer=q_explainer,
                    localizer=localizer,
                    store=store,
                    audit=audit,
                    lang=lang,
                    phone=phone,
                    tree_id=chosen.id,
                    policy_rules=policy_matcher.rules_for_ids(obj.policy_rule_ids, case, message),
                )

        # 3b) No ready card: the router's decision (from step 1) picks the lane.
        #     A covered specific issue always enters its tree, never RAG/greeting.
        route = analysis.route
        if route is Route.GREETING and case.active_tree is None and coverage.issue is None:
            await store.save(case)
            await _audit(audit, case, OUTCOME_GREETING, ROUTE_GREETING)
            return _resp(case, _GREETING.get(lang, _GREETING["uz"]))
        if route is Route.RAG and coverage.issue is None:
            # Prefer the authoritative law: a situation-specific VMQ-778 rule answers
            # a standalone legal question before the looser KB retrieval does (the KB
            # can mis-hit, e.g. return a stolen-phone FAQ to a residency question).
            if case.active_tree is None:
                policy_reply = await _maybe_policy_answer(
                    reasoning_engine, policy_composer, case, message, lang, store, audit
                )
                if policy_reply is not None:
                    return policy_reply
            reply = await _rag_answer(
                provider,
                grounding,
                interaction_log,
                case,
                message,
                lang,
                knowledge_gaps,
                learned_knowledge,
            )
            # A standalone question leaves no residue; a question mid-diagnosis
            # keeps the open case so the next message can still answer it.
            if case.active_tree is None:
                _start_fresh_case(case)
            if reply.requires_human:
                # No grounded answer: don't dead-end - offer the topics we can help
                # with so the user can pick one instead of only "contact a specialist".
                case.awaiting_menu = True
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
                case.awaiting_menu = True
                await store.save(case)
                await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_CASE)
                return await _menu(
                    case, engine.trees_for_domain(menu_domain), intro, lang, localizer
                )
            case.awaiting_menu = True
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
            composer=composer,
            q_explainer=q_explainer,
            localizer=localizer,
            store=store,
            audit=audit,
            lang=lang,
            phone=phone,
            tree_id=active_tree,
            policy_rules=policy_matcher.rules_for_ids(obj.policy_rule_ids, case, message),
        )
    if kind == "ask" and isinstance(obj, DiagnosticNode):
        # Never ask the same question twice in a row: the previous turn asked it and
        # this message did not answer it, so the customer is talking about something
        # else. Leave the tree and answer the message itself (the KB, else 1170)
        # rather than repeating the question. A request to rephrase is not this case.
        if case.last_question == obj.id and detect_style(message) is None:
            case.active_tree = None
            case.pending_node = None
            case.last_question = None
            reply = await _rag_answer(
                provider,
                grounding,
                interaction_log,
                case,
                message,
                lang,
                knowledge_gaps,
                learned_knowledge,
            )
            if not reply.requires_human:
                await store.save(case)
                await _audit(audit, case, OUTCOME_ANSWER, ROUTE_RAG, detail="repeat_question_guard")
                return reply
            case.status = CaseStatus.CALL_1170_RECOMMENDED
            case.call_1170_reason = "question_not_answered"
            await store.save(case)
            await _audit(audit, case, OUTCOME_CALL_1170, ROUTE_CASE, detail="repeat_question_guard")
            text = _UNSUPPORTED_1170.get(lang, _UNSUPPORTED_1170["uz"]).format(phone=phone)
            return _resp(case, text, done=True, requires_human=True, call_1170=True, phone=phone)
        case.last_question = obj.id
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


# §24 conversation summary: only short, categorical fact values are inlined; anything
# longer is reduced to its name, so the stored digest never carries free-form PII.
_SAFE_FACT_VALUE = re.compile(r"^[\w./-]{1,24}$")


def _safe_fact_tokens(case: CaseState) -> list[str]:
    """Known facts as "name=value" for short categorical values, else just the name."""
    tokens: list[str] = []
    for name, value in case.known_facts().items():
        tokens.append(f"{name}={value}" if _SAFE_FACT_VALUE.match(value or "") else name)
    return tokens


def _build_conversation_summary(case: CaseState) -> str:
    """A short, PII-safe digest of the case state after a turn (spec §24)."""
    parts: list[str] = []
    goal = case.current_intent or case.user_goal
    if goal:
        parts.append(f"goal={goal}")
    if case.domain:
        parts.append(f"domain={case.domain}")
    parts.append(f"status={case.status.value}")
    tokens = _safe_fact_tokens(case)
    if tokens:
        parts.append("facts=" + ",".join(tokens))
    if case.last_question:
        parts.append(f"open_q={case.last_question}")
    return "; ".join(parts)


async def _finalize_turn(
    request: Request, payload: ConverseCaseRequest, response: ConverseCaseResponse
) -> ConverseCaseResponse:
    """Run the §26 quality gate and refresh the §24 summary after a turn.

    The gate is a last-resort safety net: if a composed reply slipped through claiming
    a live-system lookup the assistant cannot make, it is replaced with an honest
    abstention instead of being shown. The conversation digest is then rebuilt from the
    post-turn state so the stored case stays legible without keeping the raw messages.
    """
    store = cast(CaseStore, request.app.state.case_store)
    case = await store.get(payload.session_id)
    if case is None:
        return response
    issues = check_reply(
        response.reply,
        option_values=[o.value for o in response.options],
        done=response.done,
        current_intent=case.current_intent,
    )
    if CAPABILITY_CLAIM in issues and not response.requires_human:
        lang = detect_language(redact_likely_pii(payload.message), default=payload.language)
        fallback = _NO_EVIDENCE_REPLY.get(lang, _NO_EVIDENCE_REPLY["uz"])
        response = response.model_copy(
            update={"reply": fallback, "requires_human": True, "done": True}
        )
    case.conversation_summary = _build_conversation_summary(case)
    await store.save(case)
    return response


@router.post("/converse", response_model=ConverseCaseResponse)
async def assistant_converse(
    payload: ConverseCaseRequest, request: Request
) -> ConverseCaseResponse:
    """One conversation turn, the quality gate, then capture it to the interaction log."""
    response = await _converse_turn(payload, request)
    response = await _finalize_turn(request, payload, response)
    await _log_interaction(request, payload, response)
    return response


class CaseStateOut(BaseModel):
    exists: bool
    session_id: str
    status: str | None = None
    domain: str | None = None
    resolution_card_id: str | None = None
    awaiting_result: bool = False
    done: bool = False


@router.get("/case/{session_id}", response_model=CaseStateOut)
async def assistant_case(session_id: str, request: Request) -> CaseStateOut:
    """The current case state for a session, so a reopened page continues the case.

    Only the server-held state is returned (status, domain, the open card); message
    history is never stored, so nothing personal is kept to rehydrate.
    """
    store = cast(CaseStore, request.app.state.case_store)
    case = await store.get(session_id)
    if case is None:
        return CaseStateOut(exists=False, session_id=session_id)
    done = case.status in (
        CaseStatus.RESOLVED,
        CaseStatus.CALL_1170_RECOMMENDED,
        CaseStatus.HANDOFF,
    )
    return CaseStateOut(
        exists=True,
        session_id=session_id,
        status=case.status.value,
        domain=case.domain,
        resolution_card_id=case.resolution_card_id,
        awaiting_result=case.status in AWAITING_OUTCOME,
        done=done,
    )


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
