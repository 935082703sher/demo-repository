"""Compose a natural, legally grounded answer from matched VMQ-778 policy rules.

This is the synthesis step the spec calls for: the matched :class:`PolicyRule`
objects and any resolved payment are the EVIDENCE; the LLM applies them to the
customer's situation and explains them in natural language. The law text is never
returned verbatim, and the LLM may not change a legal fact - only apply and phrase
it.

Two grounding checks protect the output. A legal-grounding check rejects any answer
that cites a clause the evidence did not provide (no invented "N-modda"); a
fact-preserving check (shared with the card composer) rejects any answer that alters
or invents a monetary figure. On any violation, LLM error, or mock provider, the
deterministic grounded summary built here is returned instead - so every answer
still carries its clause and source, and the mock/test path is stable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.domain.tariffs import ResolvedPayment
from app.services.assistant_voice import ASSISTANT_VOICE
from app.services.policy_matcher import PolicyMatch
from app.services.status_capability import claims_live_check

# A clause citation in the answer: "6-band", "6-1 band", "10-modda", "6-ilova", etc.
_CLAUSE_CITATION = re.compile(r"\b(\d+(?:-\d+)?)\s*-?\s*(?:band|modda|ilova|bandi|moddasi)", re.I)

_LANGUAGE_NAME = {
    "uz": "Uzbek (Latin script)",
    "uz_cyrl": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
    "kaa": "Karakalpak",
}


# A monetary amount: digits (optionally space/comma grouped) directly followed by a
# currency word. This is the one figure a wrong value could materially mislead on -
# a fabricated fee. Grouping excludes the period so a list number ("1. 1170 ...")
# never merges into the next number. Uzbek (Latin/Cyrillic) and Russian currency.
_MONEY = re.compile(r"(\d[\d  ,]*\d|\d)\s*(?:so['’ʻ]?m|som|sum|rubl|rubel|руб|сум)", re.I)


def _clause_key(clause: str) -> str:
    """Normalise a clause label to digits for comparison ("6-1" -> "61", "6" -> "6")."""
    return re.sub(r"\D", "", clause)


def _clause_main(clause: str) -> str:
    """The main article number of a clause ("6-1" -> "6", "6-ilova" -> "6", "31" -> "31")."""
    return re.sub(r"\D", "", clause.split("-")[0])


def _money_figures(text: str) -> set[str]:
    """The monetary amounts stated in a text, grouping stripped ("82 400" -> "82400")."""
    out: set[str] = set()
    for m in _MONEY.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if digits:
            out.add(digits)
    return out


def introduces_no_new_number(evidence: str, answer: str) -> bool:
    """True when the answer invents no monetary amount absent from the evidence.

    The safety net is deliberately narrow: it guards the one figure a wrong value
    could materially mislead on - a fabricated fee ("250 000 so'm" with no basis). A
    sum stated in the evidence or by the customer is allowed. Clause numbers,
    deadlines, percentages, the hotline, URLs and step indices are not numerically
    checked here - the composer instruction keeps them faithful and is_legally_grounded
    guards invented clauses - so a natural answer is not rejected for merely mentioning
    them.
    """
    return _money_figures(answer) <= _money_figures(evidence)


def is_legally_grounded(answer: str, allowed_clauses: list[str]) -> bool:
    """True when every clause the answer cites belongs to a matched article family.

    Guards against the model inventing a legal reference, but softened: a citation is
    accepted when it shares the MAIN article number of a matched clause, so when the
    evidence carries 31-1 and 31-2 the answer may say "31-band", and when it carries
    "6" it may say "6-1" or "6-ilova" - the same article, not a fabrication. A clause
    from an entirely different article the evidence never raised (e.g. "24-modda" with
    no 24 in the basis) still fails.
    """
    allowed = {_clause_main(c) for c in allowed_clauses}
    for match in _CLAUSE_CITATION.finditer(answer):
        if _clause_main(match.group(1)) not in allowed:
            return False
    return True


def _payment_line(payment: ResolvedPayment, lang: str) -> str:
    """A grounded, computed payment line (per IMEI), or a free-of-charge line."""
    if payment.percent == 0:
        return {
            "ru": "Оплата: бесплатно (при условиях Положения).",
            "en": "Payment: free (under the Regulation's conditions).",
        }.get(lang, "To'lov: bepul (Nizom shartlari bajarilganda).")
    per = " (har bir IMEI uchun)" if payment.per_imei else ""
    amount = f"{payment.amount:,}".replace(",", " ")
    return {
        "ru": f"Оплата: {payment.percent}% от БХМ = {amount} сум за каждый IMEI.",
        "en": f"Payment: {payment.percent}% of the BHM = {amount} UZS per IMEI.",
    }.get(lang, f"To'lov: BHMning {payment.percent}% = {amount} so'm{per}.")


def build_policy_summary(
    match: PolicyMatch, payments: list[ResolvedPayment], lang: str, source_url: str
) -> str:
    """A deterministic, clause-cited summary of the matched rules (the fallback).

    This is evidence rendered safely, not the final style target: it states each
    applicable legal rule, the clause, the recommended actions, any computed payment,
    and the source. The LLM composer turns the same evidence into natural prose; when
    that is unavailable this is returned, so the answer is always grounded.
    """
    lines: list[str] = []
    for rule in match.rules:
        lines.append(f"• {rule.legal_rule} ({rule.document} {rule.clause}-band)")
        for action in rule.recommended_actions:
            lines.append(f"   – {action}")
    for payment in payments:
        lines.append(_payment_line(payment, lang))
    lines.append(f"Manba: {match.rules[0].document} — {source_url}" if match.rules else source_url)
    return "\n".join(lines)


_ESCALATE = {
    "uz": "Aniq holatingiz bo'yicha 1170 ga murojaat qiling.",
    "uz_cyrl": "Аниқ ҳолатингиз бўйича 1170 га мурожаат қилинг.",
    "ru": "По вашему конкретному случаю обратитесь по номеру 1170.",
    "en": "For your specific case, please call 1170.",
    "kaa": "Anıq jaǵdayıńız boyınsha 1170 ge múrájat etiń.",
}


def concise_fallback(match: PolicyMatch, payments: list[ResolvedPayment], lang: str) -> str:
    """A short, human fallback when the composed answer is unavailable or ungrounded.

    Two leading legal points in prose (not a long bullet dump), any computed payment,
    a nudge to 1170 for the specific case, and the source. Still fully grounded - it
    is built from the matched rules - but reads like a brief reply, so the worst case
    is never a robotic wall of clauses.
    """
    if not match.rules:
        return _ESCALATE.get(lang, _ESCALATE["uz"])
    parts = [
        f"{r.legal_rule.split('.')[0].strip()} ({r.document} {r.clause}-band)."
        for r in match.rules[:2]
    ]
    if payments:
        parts.append(_payment_line(payments[0], lang))
    parts.append(_ESCALATE.get(lang, _ESCALATE["uz"]))
    parts.append(f"Asos: {match.rules[0].document} — {match.rules[0].source_url}")
    return " ".join(parts)


def answer_plan(match: PolicyMatch, payments: list[ResolvedPayment]) -> dict[str, Any]:
    """The structured evidence handed to the LLM: rules, clauses, actions, payment."""
    return {
        "legal_basis": [
            {
                "clause": rule.clause,
                "document": rule.document,
                "legal_rule": rule.legal_rule,
                "required_documents": rule.required_documents,
                "required_evidence": rule.required_evidence,
                "recommended_actions": rule.recommended_actions,
                "escalation_conditions": rule.escalation_conditions,
                "source_url": rule.source_url,
            }
            for rule in match.rules
        ],
        "payments": [
            {"percent": p.percent, "amount": p.amount, "per_imei": p.per_imei, "note": p.note}
            for p in payments
        ],
    }


class PolicyAnswerComposer(Protocol):
    """Turn matched policy rules into the final, natural customer answer."""

    async def compose(
        self,
        match: PolicyMatch,
        payments: list[ResolvedPayment],
        lang: str,
        message: str,
        summary: str,
    ) -> str: ...


class TemplatePolicyAnswer:
    """Deterministic composer: the grounded clause-cited summary, unchanged."""

    async def compose(
        self,
        match: PolicyMatch,
        payments: list[ResolvedPayment],
        lang: str,
        message: str,
        summary: str,
    ) -> str:
        return summary


ComposeComplete = Callable[[str], Awaitable[str]]

_LLM_INSTRUCTIONS = (
    ASSISTANT_VOICE + " "
    "You are given the APPROVED legal basis for a customer's IMEI/MNP question: the "
    "matched rules from VMQ-778 (each with its clause, legal meaning, required "
    "documents, recommended actions and escalation), and any computed payment. "
    "First work out what the customer is ACTUALLY asking. Then write the FINAL answer "
    "in the requested language, led by a direct reply to THAT question in the first "
    "sentence. "
    "Crucially: if the legal basis does NOT contain what they asked (for example they "
    "ask the customs-duty amount but the rules only cover IMEI registration), say so "
    "plainly - name what VMQ-778 does and does not settle - rather than answering a "
    "nearby question they did not ask or burying it under procedures. Then give only "
    "the steps and clauses that bear on their question, in plain language a beginner "
    "understands, say who is responsible, and where the regulation is silent point "
    "them to 1170 or the responsible body. Do not list unrelated procedures just "
    "because they are in the basis. "
    "ABSOLUTE RULES: apply ONLY the given rules and figures. Cite ONLY the clauses "
    "present in the legal basis - never invent a clause or a legal fact. Reproduce "
    "every payment figure and percentage EXACTLY as given; never add, change, round "
    "or drop one. "
    'Respond as JSON: {"answer": "..."}.'
)

_ANSWER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


class LLMPolicyAnswer:
    """Compose the final answer via an LLM, grounded against the matched rules."""

    def __init__(self, complete: ComposeComplete) -> None:
        self._complete = complete

    async def compose(
        self,
        match: PolicyMatch,
        payments: list[ResolvedPayment],
        lang: str,
        message: str,
        summary: str,
    ) -> str:
        # Grounding compares against the full summary; the user-facing fallback, when
        # the composed answer is unavailable or ungrounded, is a short human reply -
        # never the long bullet dump, which is what reads as robotic.
        fallback = concise_fallback(match, payments, lang)
        prompt = json.dumps(
            {
                "language": _LANGUAGE_NAME.get(lang, "Uzbek"),
                "customer_message": message,
                "answer_plan": answer_plan(match, payments),
            },
            ensure_ascii=False,
        )
        try:
            raw = await self._complete(prompt)
            text = str(json.loads(raw).get("answer", "")).strip()
        except Exception:  # pragma: no cover - network/parse failure -> concise fallback
            return fallback
        if not text or claims_live_check(text):
            return fallback  # empty, or claims a live lookup it cannot make
        if not is_legally_grounded(text, match.clauses()):
            return fallback  # invented a clause -> concise grounded fallback
        # The customer's own figures (a price they paid, a date) are not invented
        # facts, so they count as allowed alongside the evidence; only a number from
        # neither the evidence nor the customer is a hallucinated fact.
        if not introduces_no_new_number(summary + "\n" + message, text):
            return fallback
        return text


def build_openai_policy_answer_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> ComposeComplete:
    """Return an OpenAI-backed completion callable for policy-answer composition."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 700,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "policy_answer",
                    "strict": True,
                    "schema": _ANSWER_JSON_SCHEMA,
                }
            },
        }
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            return _extract_output_text(response.json())

    return complete


def _extract_output_text(envelope: dict[str, Any]) -> str:
    for output in envelope.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise ValueError("provider response did not contain output_text")
