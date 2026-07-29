"""Deterministic multilingual classifier coverage."""

import pytest

from app.domain.enums import Category
from app.services.classifier import RequestClassifier


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("My IMEI registration failed", Category.IMEI),
        ("My MNP transfer has a problem", Category.MNP),
        ("The city code listing is wrong", Category.NUMBER_CODES),
        ("Mobile internet signal is weak", Category.NETWORK_QUALITY),
        ("The RTMC website shows an error", Category.WEBSITE_ISSUE),
        ("I have a different RTMC matter", Category.OTHER),
        ("IMEI xizmatida xato bor", Category.IMEI),
        ("MNP raqam ko'chirish ishlamayapti", Category.MNP),
        ("Сайт RTMC показывает ошибку", Category.WEBSITE_ISSUE),
        ("Мобильный интернет работает медленно", Category.NETWORK_QUALITY),
    ],
)
def test_all_categories(message: str, expected: Category) -> None:
    result = RequestClassifier().classify(message)

    assert result.category is expected


def test_unknown_request_falls_back_to_other() -> None:
    result = RequestClassifier().classify("Please help with my unusual RTMC matter")

    assert result.category is Category.OTHER
    assert result.requires_clarification is True
