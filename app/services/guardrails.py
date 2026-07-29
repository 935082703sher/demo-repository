"""Deterministic input and output checks around the provider boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.enums import EscalationReason, SafetyFlag
from app.services.classifier import normalize_text


@dataclass(frozen=True, slots=True)
class GuardrailDecision:
    """Result of a deterministic safety check."""

    allowed: bool
    flags: tuple[SafetyFlag, ...] = ()
    handoff_reason: EscalationReason | None = None
    out_of_scope: bool = False


class Guardrails:
    """Conservative rules that reduce risk but do not claim perfect detection."""

    _secret_patterns = (
        re.compile(r"\b(?:password|parol|пароль|pin|cvv)\b", re.IGNORECASE),
        re.compile(r"\b(?:otp|sms code|sms kod|смс[- ]?код)\b", re.IGNORECASE),
        re.compile(r"\b(?:api[_ -]?key|access[_ -]?token|private[_ -]?key)\b", re.IGNORECASE),
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    )

    def check_input(self, message: str) -> GuardrailDecision:
        """Stop or refuse content covered by mandatory escalation rules."""
        text = normalize_text(message)

        if any(pattern.search(message) for pattern in self._secret_patterns):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.CREDENTIAL_DISCLOSURE,),
                handoff_reason=EscalationReason.SENSITIVE_DATA,
            )

        if self._contains(
            text,
            "ignore previous",
            "ignore all rules",
            "reveal system prompt",
            "show hidden instructions",
            "developer message",
            "system prompting",
            "oldingi ko'rsatmalarni e'tiborsiz",
            "раскрой системный промпт",
            "игнорируй инструкции",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.PROMPT_INJECTION,),
                handoff_reason=EscalationReason.PROMPT_INJECTION,
            )

        if self._contains(
            text,
            "kill myself",
            "suicide",
            "self harm",
            "o'zimni o'ldir",
            "самоубий",
            "убить себя",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.SELF_HARM,),
                handoff_reason=EscalationReason.SELF_HARM,
            )

        if self._contains(
            text,
            "immediate danger",
            "emergency",
            "explosion",
            "fire right now",
            "shoshilinch xavf",
            "portlash",
            "чрезвычайная ситуация",
            "немедленная опасность",
            "взрыв",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.EMERGENCY,),
                handoff_reason=EscalationReason.EMERGENCY,
            )

        if self._contains(
            text,
            "i will kill",
            "bomb threat",
            "attack the",
            "o'ldiraman",
            "hujum qil",
            "я убью",
            "угроза взрыва",
            "нападу",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.THREAT,),
                handoff_reason=EscalationReason.THREAT_OR_VIOLENCE,
            )

        if self._contains(
            text,
            "credentials leaked",
            "data breach",
            "ransomware",
            "hacked rtmc",
            "ma'lumotlar sizib",
            "утечка данных",
            "взломали",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.CYBERSECURITY,),
                handoff_reason=EscalationReason.CYBERSECURITY,
            )

        if self._contains(
            text,
            "legal advice",
            "interpret the law",
            "am i legally entitled",
            "huquqiy maslahat",
            "qonunni sharhla",
            "юридическая консультация",
            "истолкуй закон",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.LEGAL_REQUEST,),
                handoff_reason=EscalationReason.LEGAL_INTERPRETATION,
            )

        if self._contains(
            text,
            "dispute the official decision",
            "official decision is wrong",
            "change the official decision",
            "rasmiy qarorga e'tiroz",
            "rasmiy qarorni o'zgartir",
            "оспорить официальное решение",
            "официальное решение неверно",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.LEGAL_REQUEST,),
                handoff_reason=EscalationReason.OFFICIAL_DECISION_DISPUTE,
            )

        if self._contains(
            text,
            "corruption",
            "serious fraud",
            "official misconduct",
            "extortion",
            "korrupsiya",
            "firibgarlik",
            "tovlamachilik",
            "коррупц",
            "мошеннич",
            "вымогатель",
        ):
            return GuardrailDecision(
                allowed=False,
                handoff_reason=EscalationReason.MISCONDUCT_ALLEGATION,
            )

        if self._contains(
            text,
            "weather",
            "capital of",
            "recipe",
            "football score",
            "movie recommendation",
            "ob-havo",
            "retsept",
            "погода",
            "рецепт",
            "столица франции",
        ):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.OUT_OF_SCOPE,),
                out_of_scope=True,
            )

        return GuardrailDecision(allowed=True)

    def check_output(self, text: str, *, grounded: bool) -> GuardrailDecision:
        """Reject provider text that could imply unsupported official authority."""
        normalized = normalize_text(text)
        prohibited = (
            "officially registered",
            "your case number is",
            "rtmc has decided",
            "guaranteed within",
            "appeal was accepted",
            "rasmiy ro'yxatdan o'tkazildi",
            "murojaat raqamingiz",
            "rasmiy qaror",
            "официально зарегистрировано",
            "номер вашего обращения",
            "rtmc принял решение",
        )
        if any(phrase in normalized for phrase in prohibited):
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.UNSUPPORTED_CLAIM,),
                handoff_reason=EscalationReason.OUTPUT_VALIDATION_FAILED,
            )
        if text.strip() and not grounded:
            return GuardrailDecision(
                allowed=False,
                flags=(SafetyFlag.UNSUPPORTED_CLAIM,),
                handoff_reason=EscalationReason.OUTPUT_VALIDATION_FAILED,
            )
        return GuardrailDecision(allowed=True)

    @staticmethod
    def _contains(text: str, *phrases: str) -> bool:
        return any(phrase in text for phrase in phrases)
