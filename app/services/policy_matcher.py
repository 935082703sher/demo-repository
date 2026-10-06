"""Select the VMQ-778 policy rules that fit a customer's situation.

This is the bridge from a free-form case to the authoritative rules: it derives a
set of controlled situation signals from the structured facts and the message, then
returns the :class:`PolicyRule` objects whose ``applies_if`` / ``excludes_if``
conditions those signals satisfy, most specific first and in force on the enquiry
date. The rules are evidence for the answer layer - the matcher never writes the
customer-facing text and never invents a rule that is not in the data file.

Signals are a small, fixed vocabulary (resident vs non-resident, local purchase vs
personal import, multi-IMEI device, clone, roaming, ...). Deriving them from typed
facts first and keywords second keeps a passing mention from being mistaken for the
customer's actual situation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.domain.case_state import CaseState
from app.domain.policy import PolicyBundle, PolicyRule
from app.services.fact_extraction import _normalize

# message keyword -> signal. Keywords are in the normalized Latin form produced by
# _normalize (Cyrillic transliterated, apostrophes dropped).
_KEYWORD_SIGNALS: dict[str, tuple[str, ...]] = {
    "local_purchase": (
        "dokondan",
        "dokonda",
        "magazin",
        "ozbekistondan sotib",
        "mahalliy sotuvchi",
    ),
    "bought_from_private_person": (
        "tanishimdan",
        "qoldan oldim",
        "boshqa odamdan",
        "ishlatilgan telefon",
        "b u telefon",
    ),
    "imported_by_commercial_importer": (
        "import qiluvchi",
        "importchi",
        "yuk deklarats",
        "im 40",
        "im40",
        "partiya",
        "optom",
    ),
    "user_is_nonresident": (
        "norezident",
        "xorijiy fuqaro",
        "chet el fuqaro",
        "chet ellik",
        "turist",
        "vaqtincha kelgan",
        "inostranets",
        "nerezident",
    ),
    "roaming_only_no_local_network_event": ("rouming", "roaming", "v rouminge"),
    "imei_cloned_or_undetermined": (
        "klon",
        "klonlangan",
        "aniqlanmagan imei",
        "klonirovan",
        "ne opredelen",
    ),
    "imei_blacklisted": (
        "qora royxat",
        "qora ruyxat",
        "bloklangan",
        "bloklandi",
        "chyornyy spisok",
    ),
    "multi_imei_device": (
        "ikkinchi imei",
        "ikkita imei",
        "2 imei",
        "ikki imei",
        "esim",
        "ikki sim",
        "ikkala sim",
        "dual sim",
        "vtoroy imei",
    ),
    "within_30_days_of_first_network_event": ("30 kun ichida", "yangi oldim", "hozirgina oldim"),
    "after_30_days_of_first_network_event": (
        "30 kundan keyin",
        "30 kundan oshdi",
        "muddat otib",
        "muddati otgan",
        "kech qoldim",
    ),
    "diplomatic_mission": ("elchixona", "diplomat", "konsul", "diplomaticheskiy"),
}


@dataclass(frozen=True)
class PolicyMatch:
    """The rules selected for a situation, with the signals that selected them."""

    rules: list[PolicyRule] = field(default_factory=list)
    signals: set[str] = field(default_factory=set)

    def clauses(self) -> list[str]:
        """The distinct clauses cited by the matched rules, in order."""
        seen: list[str] = []
        for rule in self.rules:
            if rule.clause not in seen:
                seen.append(rule.clause)
        return seen


def derive_signals(case: CaseState, message: str) -> set[str]:
    """Map the typed case facts and the message to controlled situation signals."""
    signals: set[str] = set()
    facts = case.known_facts()

    origin = facts.get("device_origin")
    if origin == "local":
        signals.add("local_purchase")
    elif origin == "imported":
        signals.add("personal_import")
    if facts.get("affected_sim") in ("second", "both"):
        signals.add("multi_imei_device")

    norm = _normalize(message)
    for signal, keywords in _KEYWORD_SIGNALS.items():
        if any(keyword in norm for keyword in keywords):
            signals.add(signal)

    # A commercial importer is not a personal import; the stronger signal wins.
    if "imported_by_commercial_importer" in signals:
        signals.discard("personal_import")
    # Residency defaults to resident unless a non-resident/diplomatic signal appears,
    # so resident-scoped rules apply to the common case without a special statement.
    if "user_is_nonresident" not in signals and "diplomatic_mission" not in signals:
        signals.add("user_is_resident")
    return signals


class PolicyMatcher:
    """Load the policy bundle and return the rules that fit a situation."""

    def __init__(self, bundle: PolicyBundle) -> None:
        self._bundle = bundle

    @classmethod
    def from_json(cls, path: Path) -> PolicyMatcher:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(PolicyBundle.model_validate(raw))

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._bundle.rules)

    def rules_for_ids(
        self, rule_ids: list[str], case: CaseState, message: str, *, when: date | None = None
    ) -> list[PolicyRule]:
        """The named rules that ground a decision-tree card, in the card's order.

        The card author has already asserted these rules are the legal basis for the
        resolution, so a rule is kept unless its ``excludes_if`` actually conflicts
        with the known situation (e.g. a resident-only rule when the customer is a
        non-resident). Unlike :meth:`match`, a missing ``applies_if`` signal does not
        drop a declared rule - the resolution is this card precisely because these
        clauses apply. Out-of-force rules are still excluded.
        """
        on = when or date.today()
        signals = derive_signals(case, message)
        by_id = {rule.rule_id: rule for rule in self._bundle.rules}
        return [
            rule
            for rule_id in rule_ids
            if (rule := by_id.get(rule_id)) is not None
            and rule.is_effective_on(on)
            and not any(signal in signals for signal in rule.excludes_if)
        ]

    def match(self, case: CaseState, message: str, *, when: date | None = None) -> PolicyMatch:
        """Return the in-force rules whose conditions the situation satisfies.

        Rules are ordered most specific first (more conditions), so a situation-exact
        rule outranks a general one. A rule with no ``applies_if`` is a general rule
        for its topic and is included whenever its ``excludes_if`` is clear.
        """
        on = when or date.today()
        signals = derive_signals(case, message)
        selected = [
            rule
            for rule in self._bundle.rules
            if rule.is_effective_on(on) and rule.matches(signals)
        ]
        selected.sort(key=lambda rule: rule.specificity(), reverse=True)
        return PolicyMatch(rules=selected, signals=signals)
