"""The registration payment is computed from the law's percentage and a versioned
BHM - never a hardcoded sum. The amounts must match the approved resolution-card
figures (20% = 82 400, 25% = 103 000), and pricing abstains when it cannot be
grounded (unknown formula, or no BHM for the date)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.domain.tariffs import TariffConfig

_TARIFFS = Path("app/data/tariffs.json")


def _config() -> TariffConfig:
    return TariffConfig.from_json(_TARIFFS)


def test_within_30_days_is_20_percent_of_bhm() -> None:
    payment = _config().resolve("physical_person_within_30_days", date(2026, 1, 1))
    assert payment is not None
    assert payment.percent == 20
    assert payment.amount == 82_400  # 20% of 412 000 - matches the approved card
    assert payment.per_imei is True


def test_after_30_days_is_25_percent_of_bhm() -> None:
    payment = _config().resolve("physical_person_after_30_days", date(2026, 1, 1))
    assert payment is not None
    assert payment.amount == 103_000  # 25% of 412 000 - matches the approved card


def test_importer_and_manufacturer_rates() -> None:
    config = _config()
    importer = config.resolve("commercial_importer", date(2026, 1, 1))
    manufacturer = config.resolve("manufacturer", date(2026, 1, 1))
    assert importer is not None and importer.amount == 82_400  # 20%
    assert manufacturer is not None and manufacturer.amount == 41_200  # 10%


def test_roaming_is_free_without_needing_a_bhm() -> None:
    payment = _config().resolve("roaming_subscriber", date(2026, 1, 1))
    assert payment is not None and payment.amount == 0 and payment.percent == 0


def test_unknown_formula_abstains() -> None:
    assert _config().resolve("no_such_formula", date(2026, 1, 1)) is None


def test_no_bhm_for_date_abstains_rather_than_guessing() -> None:
    # Before any configured BHM takes effect, a percentage cannot be priced.
    assert _config().resolve("physical_person_within_30_days", date(2000, 1, 1)) is None


def test_bhm_amount_is_not_hardcoded_in_percent_formulas() -> None:
    # The formula carries only the percentage; the sum depends on the versioned BHM.
    config = _config()
    assert config.formulas["physical_person_within_30_days"].percent == 20
    assert config.bhm_on(date(2026, 1, 1)) is not None
