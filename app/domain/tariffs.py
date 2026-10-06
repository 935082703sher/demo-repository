"""Versioned tariff source: the IMEI-registration payment, resolved, not hardcoded.

VMQ-778 fixes the payment as a *percentage* of the BHM (bazaviy hisoblash miqdori,
the base calculation unit), separately for each IMEI code: 20% for a physical person
who registers within 30 calendar days of the first network event, 25% afterwards,
20% for an importer, 10% for a manufacturer, 20% for a diplomatic mission, and free
for a roaming subscriber meeting the Regulation's conditions (6-ilova).

The percentage is law and lives with the policy rule. The BHM itself changes by
separate decree, so it is kept here as a *versioned* value with effective dates: the
amount shown to a customer is computed (BHM x percent) for the date of the enquiry,
and a BHM change is one data edit - never a code change and never a hardcoded sum.

The BHM amount below is the value consistent with the approved figures already used
in the resolution cards (412 000 so'm -> 20% = 82 400, 25% = 103 000). Confirm the
current BHM against the official source before a production deployment; only this
single value, with its effective date, needs updating.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class BhmValue(BaseModel):
    """A BHM amount in force over a date range (versioned, never hardcoded in code)."""

    model_config = ConfigDict(extra="forbid")

    amount: int
    currency: str = "UZS"
    effective_from: date
    effective_to: date | None = None
    source: str


class PaymentFormula(BaseModel):
    """A payment as a percentage of the BHM, per IMEI code, for one applicant class."""

    model_config = ConfigDict(extra="forbid")

    percent: int
    per_imei: bool = True
    note: str = ""


class ResolvedPayment(BaseModel):
    """A computed payment: the law's percentage applied to the current BHM."""

    model_config = ConfigDict(extra="forbid")

    percent: int
    bhm: int
    amount: int
    currency: str
    per_imei: bool
    note: str
    bhm_source: str


class TariffConfig(BaseModel):
    """BHM history plus the law's payment formulas, loaded from the data file."""

    model_config = ConfigDict(extra="forbid")

    bhm: list[BhmValue] = Field(default_factory=list)
    formulas: dict[str, PaymentFormula] = Field(default_factory=dict)

    @classmethod
    def from_json(cls, path: Path) -> TariffConfig:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def bhm_on(self, when: date) -> BhmValue | None:
        """The BHM value in force on the given date, if any is configured."""
        candidates = [
            value
            for value in self.bhm
            if value.effective_from <= when
            and (value.effective_to is None or when <= value.effective_to)
        ]
        return max(candidates, key=lambda value: value.effective_from) if candidates else None

    def resolve(self, formula_ref: str, when: date) -> ResolvedPayment | None:
        """Compute a payment for a formula on a date, or None when it cannot be priced.

        Returns None (rather than a guessed figure) when the formula is unknown or no
        BHM value covers the date, so the caller abstains instead of inventing a sum.
        A free (0%) formula resolves to a zero amount without needing a BHM value.
        """
        formula = self.formulas.get(formula_ref)
        if formula is None:
            return None
        if formula.percent == 0:
            return ResolvedPayment(
                percent=0,
                bhm=0,
                amount=0,
                currency="UZS",
                per_imei=formula.per_imei,
                note=formula.note,
                bhm_source="n/a (free)",
            )
        value = self.bhm_on(when)
        if value is None:
            return None
        return ResolvedPayment(
            percent=formula.percent,
            bhm=value.amount,
            amount=value.amount * formula.percent // 100,
            currency=value.currency,
            per_imei=formula.per_imei,
            note=formula.note,
            bhm_source=value.source,
        )
