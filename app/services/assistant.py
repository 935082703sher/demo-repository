"""Controlled orchestration for chat, retrieval, and human handoff."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid4

from app.domain.enums import (
    Category,
    ConversationState,
    EscalationReason,
    Language,
    ResponseType,
    SafetyFlag,
)
from app.domain.schemas import ChatRequest, ChatResponse, LLMRequest, SourceReference
from app.i18n.messages import out_of_scope_message, rate_limit_message, usage_limit_message
from app.providers.errors import ProviderOutputError
from app.services.classifier import RequestClassifier, is_complaint_like, normalize_text
from app.services.complaint_drafts import missing_fields_for
from app.services.generation import GroundedGenerationService
from app.services.grounding import GroundingValidator
from app.services.guardrails import Guardrails
from app.services.human_handoff import handoff_message
from app.services.knowledge import KnowledgeService
from app.services.scope import ScopeService, ScopeStatus
from app.services.usage_limits import RequestRateLimitService, UsageLimitService

_LANGUAGE_SELECTION = (
    "RTMC AI yordamchisi / ИИ-помощник RTMC / RTMC AI assistant. "
    "Tilni tanlang / Выберите язык / Select a language: uz, ru, or en."
)

_AI_DISCLOSURE = {
    Language.UZ: (
        "Siz AI yordamchisi bilan muloqot qilyapsiz. U faqat tasdiqlangan RTMC "
        "ma'lumotlari asosida yo'l-yo'riq beradi va murojaat loyihasini tayyorlashga "
        "yordam beradi. Loyihani ko'rib chiqib, “Yuborish” tugmasini bosmaguningizcha "
        "hech narsa yuborilmaydi. Siz inson operatorini so'rashingiz mumkin."
    ),
    Language.RU: (
        "Вы общаетесь с ИИ-помощником. Он предоставляет рекомендации только по "
        "утверждённой информации RTMC и помогает подготовить проект обращения. "
        "Ничего не отправляется, пока Вы не проверите проект и не нажмёте "
        "«Отправить». Вы можете запросить оператора."
    ),
    Language.EN: (
        "You are interacting with an AI assistant. It provides guidance only from "
        "approved RTMC information and can help prepare an appeal draft. Nothing is "
        "submitted until you review the draft and press “Submit.” You may request a human."
    ),
}

_CLARIFY_OTHER = {
    Language.UZ: "RTMC bilan bog'liq masalani va kerakli natijani qisqacha bayon qiling.",
    Language.RU: "Кратко опишите вопрос, связанный с RTMC, и желаемый результат.",
    Language.EN: "Briefly describe the RTMC-related matter and your desired outcome.",
}

_FOLLOW_UP: dict[Language, dict[Category, dict[str, str]]] = {
    Language.UZ: {
        Category.IMEI: {
            "request_kind": "Bu ma'lumot so'rovi yoki shikoyatmi?",
            "action_attempted": "IMEI xizmatida qanday amalni bajardingiz?",
            "observed_result": "Qanday natija yoki xato ko'rindi?",
            "event_time": "Muammo qachon yuz berdi?",
        },
        Category.MNP: {
            "request_kind": "Bu ma'lumot so'rovi yoki shikoyatmi?",
            "current_stage": "Raqam ko'chirish jarayoni qaysi bosqichda?",
            "operator": "Qaysi operator ishtirok etgan?",
            "submitted_at": "So'rov qachon yuborilgan?",
            "observed_error": "Qanday xato yoki xabar ko'rindi?",
        },
        Category.NUMBER_CODES: {
            "code_type": "Qaysi kod turi: qisqa, hududiy, shahar yoki xalqaro?",
            "country_or_region": "Qaysi mamlakat, hudud yoki xizmat nazarda tutilgan?",
            "request_kind": (
                "Sizga ma'lumot kerakmi yoki noto'g'ri ro'yxat haqida xabar bermoqchimisiz?"
            ),
        },
        Category.NETWORK_QUALITY: {
            "operator": "Qaysi mobil operator xizmatidan foydalanasiz?",
            "service_type": "Qaysi xizmat: qo'ng'iroq, SMS, mobil internet yoki boshqa?",
            "region": "Qaysi viloyatda?",
            "district": "Qaysi tuman yoki shaharda?",
            "approximate_location": "Taxminiy joylashuvni ortiqcha shaxsiy ma'lumotsiz ko'rsating.",
            "event_time": "Muammo qachon yuz berdi?",
            "frequency": "Muammo qanchalik tez-tez takrorlanadi?",
            "duration": "Har bir uzilish qancha davom etadi?",
            "impact": "Muammo xizmatdan foydalanishga qanday ta'sir qildi?",
        },
        Category.WEBSITE_ISSUE: {
            "page_url": "Qaysi sahifa yoki xizmat URL manzili ta'sirlangan?",
            "action_attempted": "Qanday amalni bajarmoqchi edingiz?",
            "error_message": "Qanday xato xabari ko'rindi?",
            "event_time": "Muammo qachon yuz berdi?",
            "device_type": "Qaysi qurilmadan foydalandingiz?",
            "browser_type": "Qaysi brauzerdan foydalandingiz?",
        },
        Category.OTHER: {},
    },
    Language.RU: {
        Category.IMEI: {
            "request_kind": "Это информационный вопрос или жалоба?",
            "action_attempted": "Какое действие Вы выполняли в сервисе IMEI?",
            "observed_result": "Какой результат или сообщение об ошибке Вы увидели?",
            "event_time": "Когда возникла проблема?",
        },
        Category.MNP: {
            "request_kind": "Это информационный вопрос или жалоба?",
            "current_stage": "На каком этапе находится перенос номера?",
            "operator": "Какой оператор участвует?",
            "submitted_at": "Когда был подан запрос?",
            "observed_error": "Какое сообщение или ошибку Вы получили?",
        },
        Category.NUMBER_CODES: {
            "code_type": "Какой тип кода: короткий, региональный, городской или международный?",
            "country_or_region": "О какой стране, регионе или услуге идёт речь?",
            "request_kind": "Вам нужна информация или Вы сообщаете о неверной записи?",
        },
        Category.NETWORK_QUALITY: {
            "operator": "Услугами какого мобильного оператора Вы пользуетесь?",
            "service_type": "Какая услуга затронута: звонки, SMS, мобильный интернет или другая?",
            "region": "В какой области возникла проблема?",
            "district": "В каком районе или городе?",
            "approximate_location": "Укажите примерное место без лишних персональных данных.",
            "event_time": "Когда возникла проблема?",
            "frequency": "Как часто повторяется проблема?",
            "duration": "Как долго длится каждый сбой?",
            "impact": "Как проблема влияет на использование услуги?",
        },
        Category.WEBSITE_ISSUE: {
            "page_url": "Какой URL страницы или сервиса затронут?",
            "action_attempted": "Какое действие Вы пытались выполнить?",
            "error_message": "Какое сообщение об ошибке отображалось?",
            "event_time": "Когда возникла проблема?",
            "device_type": "Какое устройство Вы использовали?",
            "browser_type": "Какой браузер Вы использовали?",
        },
        Category.OTHER: {},
    },
    Language.EN: {
        Category.IMEI: {
            "request_kind": "Is this an information request or a complaint?",
            "action_attempted": "What action did you attempt in the IMEI service?",
            "observed_result": "What result or error message did you see?",
            "event_time": "When did the issue occur?",
        },
        Category.MNP: {
            "request_kind": "Is this an information request or a complaint?",
            "current_stage": "What stage has the number-portability request reached?",
            "operator": "Which operator is involved?",
            "submitted_at": "When was the request submitted?",
            "observed_error": "What message or error did you receive?",
        },
        Category.NUMBER_CODES: {
            "code_type": "Which code type: short, regional, city, or international?",
            "country_or_region": "Which country, region, or service is concerned?",
            "request_kind": "Do you need information or are you reporting an incorrect listing?",
        },
        Category.NETWORK_QUALITY: {
            "operator": "Which mobile operator do you use?",
            "service_type": (
                "Which service is affected: calls, SMS, mobile data, or another service?"
            ),
            "region": "Which region is affected?",
            "district": "Which district or city is affected?",
            "approximate_location": (
                "Give an approximate location without unnecessary personal data."
            ),
            "event_time": "When did the issue occur?",
            "frequency": "How often does the issue occur?",
            "duration": "How long does each interruption last?",
            "impact": "How does the issue affect your use of the service?",
        },
        Category.WEBSITE_ISSUE: {
            "page_url": "What is the affected page or service URL?",
            "action_attempted": "What action were you trying to perform?",
            "error_message": "What visible error message did you receive?",
            "event_time": "When did the issue occur?",
            "device_type": "What type of device did you use?",
            "browser_type": "Which browser did you use?",
        },
        Category.OTHER: {},
    },
}


@dataclass(slots=True)
class _Session:
    language: Language
    clarification_count: int = 0


class AssistantService:
    """Enforce deterministic authorization and keep the provider advisory."""

    def __init__(
        self,
        classifier: RequestClassifier,
        guardrails: Guardrails,
        scope: ScopeService,
        knowledge: KnowledgeService,
        generation: GroundedGenerationService,
        grounding: GroundingValidator,
        usage_limits: UsageLimitService,
        rate_limits: RequestRateLimitService,
        approved_support_phone: str | None,
        approved_contact_url: str | None,
    ) -> None:
        self._classifier = classifier
        self._guardrails = guardrails
        self._scope = scope
        self._knowledge = knowledge
        self._generation = generation
        self._grounding = grounding
        self._usage_limits = usage_limits
        self._rate_limits = rate_limits
        self._approved_support_phone = approved_support_phone
        self._approved_contact_url = approved_contact_url
        self._sessions: dict[UUID, _Session] = {}
        self._initial_sessions: set[UUID] = set()
        self._lock = RLock()

    async def chat(self, request: ChatRequest, request_id: UUID) -> ChatResponse:
        """Process one message without granting submission authority to the provider."""
        session_id = request.session_id or uuid4()
        language = self._resolve_language(session_id, request.language)
        if request.session_id is None and language is not None:
            with self._lock:
                self._initial_sessions.add(session_id)

        safety = self._guardrails.check_input(request.message)
        if not safety.allowed:
            reason = safety.handoff_reason or EscalationReason.OUTPUT_VALIDATION_FAILED
            return self._handoff(
                request_id=request_id,
                session_id=session_id,
                language=language,
                reason=reason,
                flags=list(safety.flags),
            )

        if language is None:
            return self._base_response(
                request_id=request_id,
                session_id=session_id,
                language=None,
                state=ConversationState.LANGUAGE_SELECTION,
                response_type=ResponseType.LANGUAGE_SELECTION,
                reply=_LANGUAGE_SELECTION,
            )

        self._remember_session(session_id, language)
        rate = self._rate_limits.check(session_id)
        if not rate.allowed:
            retry_after = rate.retry_after_seconds or 1
            return self._base_response(
                request_id=request_id,
                session_id=session_id,
                language=language,
                state=ConversationState.RATE_LIMITED,
                response_type=ResponseType.RATE_LIMITED,
                reply=rate_limit_message(language, retry_after),
                remaining=0,
                retry_after_seconds=retry_after,
                human_handoff_available=True,
            )

        scope = self._scope.classify(request.message)
        if scope.status is ScopeStatus.OUT_OF_SCOPE:
            return self._base_response(
                request_id=request_id,
                session_id=session_id,
                language=language,
                state=ConversationState.CLOSED,
                response_type=ResponseType.REFUSAL,
                reply=out_of_scope_message(language),
                safety_flags=[SafetyFlag.OUT_OF_SCOPE],
            )

        if self._asks_for_human(request.message):
            return self._handoff(
                request_id=request_id,
                session_id=session_id,
                language=language,
                reason=EscalationReason.CITIZEN_REQUEST,
            )

        classification = self._classifier.classify(request.message)
        category = classification.category

        if classification.requires_clarification:
            if self._increment_clarification(session_id) > 1:
                return self._handoff(
                    request_id=request_id,
                    session_id=session_id,
                    language=language,
                    reason=EscalationReason.UNCLEAR_AFTER_CLARIFICATION,
                    category=Category.OTHER,
                )
            return self._base_response(
                request_id=request_id,
                session_id=session_id,
                language=language,
                state=ConversationState.FOLLOW_UP,
                response_type=ResponseType.FOLLOW_UP,
                category=Category.OTHER,
                reply=_CLARIFY_OTHER[language],
                fields_missing=missing_fields_for(Category.OTHER),
            )

        if is_complaint_like(request.message):
            missing = missing_fields_for(category)
            first_field = missing[0]
            return self._base_response(
                request_id=request_id,
                session_id=session_id,
                language=language,
                state=ConversationState.FOLLOW_UP,
                response_type=ResponseType.FOLLOW_UP,
                category=category,
                reply=_FOLLOW_UP[language][category][first_field],
                fields_missing=missing,
            )

        records = self._knowledge.search(request.message, language, category)
        if not records:
            return self._handoff(
                request_id=request_id,
                session_id=session_id,
                language=language,
                reason=EscalationReason.NO_APPROVED_SOURCE,
                category=category,
            )

        authorization = self._usage_limits.authorize(session_id)
        if not authorization.allowed:
            return self._base_response(
                request_id=request_id,
                session_id=session_id,
                language=language,
                state=ConversationState.USAGE_LIMIT_REACHED,
                response_type=ResponseType.USAGE_LIMIT_REACHED,
                category=category,
                reply=usage_limit_message(
                    language,
                    self._approved_support_phone,
                    self._approved_contact_url,
                ),
                limit=self._usage_limits.limit,
                remaining=0,
                reset_at=authorization.snapshot.reset_at,
                human_handoff_available=True,
            )

        try:
            result = await self._generation.generate(
                session_id,
                LLMRequest(
                    language=language,
                    question=request.message,
                    category=category,
                    source_ids=[record.document_id for record in records],
                    passages=[record.content for record in records],
                ),
            )
        except ProviderOutputError:
            return self._handoff(
                request_id=request_id,
                session_id=session_id,
                language=language,
                reason=EscalationReason.OUTPUT_VALIDATION_FAILED,
                category=category,
            )
        except Exception:
            return self._handoff(
                request_id=request_id,
                session_id=session_id,
                language=language,
                reason=EscalationReason.PROVIDER_UNAVAILABLE,
                category=category,
            )

        grounding = self._grounding.validate(result, records)
        if not grounding.allowed:
            return self._handoff(
                request_id=request_id,
                session_id=session_id,
                language=language,
                reason=EscalationReason.OUTPUT_VALIDATION_FAILED,
                category=category,
            )

        output_safety = self._guardrails.check_output(result.text, grounded=True)
        if not output_safety.allowed:
            return self._handoff(
                request_id=request_id,
                session_id=session_id,
                language=language,
                reason=EscalationReason.OUTPUT_VALIDATION_FAILED,
                category=category,
                flags=list(output_safety.flags),
            )

        sources = [
            SourceReference(
                document_id=record.document_id,
                title=record.title,
                url=record.source_url,
                version=record.version,
                demo_only=record.status.value == "demo_only",
            )
            for record in grounding.cited_records
        ]
        return self._base_response(
            request_id=request_id,
            session_id=session_id,
            language=language,
            state=ConversationState.ANSWER,
            response_type=ResponseType.ANSWER,
            category=category,
            reply=result.text,
            grounded=True,
            sources=sources,
        )

    def _handoff(
        self,
        *,
        request_id: UUID,
        session_id: UUID,
        language: Language | None,
        reason: EscalationReason,
        category: Category | None = None,
        flags: list[SafetyFlag] | None = None,
    ) -> ChatResponse:
        response_language = language or Language.EN
        return self._base_response(
            request_id=request_id,
            session_id=session_id,
            language=language,
            state=ConversationState.HUMAN_HANDOFF,
            response_type=ResponseType.HUMAN_HANDOFF,
            category=category,
            reply=handoff_message(response_language, reason),
            requires_human=True,
            handoff_reason=reason,
            safety_flags=flags or [],
        )

    def _base_response(
        self,
        *,
        request_id: UUID,
        session_id: UUID,
        language: Language | None,
        state: ConversationState,
        response_type: ResponseType,
        reply: str,
        category: Category | None = None,
        grounded: bool = False,
        sources: list[SourceReference] | None = None,
        fields_missing: list[str] | None = None,
        requires_human: bool = False,
        handoff_reason: EscalationReason | None = None,
        safety_flags: list[SafetyFlag] | None = None,
        limit: int | None = None,
        remaining: int | None = None,
        reset_at: datetime | None = None,
        retry_after_seconds: int | None = None,
        human_handoff_available: bool = False,
    ) -> ChatResponse:
        response = ChatResponse(
            request_id=request_id,
            session_id=session_id,
            language=language,
            state=state,
            response_type=response_type,
            category=category,
            reply=reply,
            grounded=grounded,
            sources=sources or [],
            fields_collected={},
            fields_missing=fields_missing or [],
            draft=None,
            consent_required=False,
            submission_allowed=False,
            requires_human=requires_human,
            handoff_reason=handoff_reason,
            safety_flags=safety_flags or [],
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after_seconds=retry_after_seconds,
            human_handoff_available=human_handoff_available,
        )
        if language is not None and self._take_initial(session_id):
            return response.model_copy(
                update={"reply": f"{_AI_DISCLOSURE[language]}\n\n{response.reply}"}
            )
        return response

    def _remember_session(self, session_id: UUID, language: Language) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                self._sessions[session_id] = _Session(language=language)
            else:
                session.language = language

    def _resolve_language(self, session_id: UUID, requested: Language | None) -> Language | None:
        """Use the server-owned language unless the request explicitly changes it."""
        if requested is not None:
            return requested
        with self._lock:
            session = self._sessions.get(session_id)
            return session.language if session is not None else None

    def _take_initial(self, session_id: UUID) -> bool:
        with self._lock:
            if session_id not in self._initial_sessions:
                return False
            self._initial_sessions.remove(session_id)
            return True

    def _increment_clarification(self, session_id: UUID) -> int:
        with self._lock:
            session = self._sessions[session_id]
            session.clarification_count += 1
            return session.clarification_count

    @staticmethod
    def _asks_for_human(message: str) -> bool:
        text = normalize_text(message)
        return any(
            phrase in text
            for phrase in (
                "human operator",
                "speak to a human",
                "person please",
                "operator kerak",
                "inson bilan gaplash",
                "оператор",
                "человек",
            )
        )
