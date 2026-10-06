"""The reply language follows the weight of the message; Uzbek is the default."""

from __future__ import annotations

from app.services.language_detect import detect_language


def test_uzbek_latin_is_uz() -> None:
    assert detect_language("telefonimni ro'yxatdan o'tkaza olmayapman") == "uz"
    assert detect_language("Registratsiya qilishim kerak") == "uz"


def test_russian_is_ru() -> None:
    assert detect_language("Здравствуйте, мне нужно зарегистрировать телефон") == "ru"
    assert detect_language("сколько стоит регистрация, это второй imei") == "ru"


def test_uzbek_cyrillic_is_uz_cyrl() -> None:
    assert detect_language("телефонимни рўйхатдан ўтказа олмаяпман, бу керак") == "uz_cyrl"


def test_english_only_on_a_clear_lead() -> None:
    assert detect_language("I need to register my phone, how can I do it") == "en"
    # A lone English-looking token is not a language switch.
    assert detect_language("outcome:success", default="uz") == "uz"


def test_mixed_follows_the_heavier_language() -> None:
    # Mostly Uzbek with a Russian greeting -> Uzbek.
    assert detect_language("Здравствуйте, telefonimni ro'yxatdan o'tkazmoqchiman uchun") == "uz"
    # Mostly Russian with one Uzbek word -> Russian.
    assert detect_language("мне нужно оплатить регистрацию за второй телефон qancha") == "ru"


def test_short_or_control_keeps_default() -> None:
    assert detect_language("ha", default="uz") == "uz"
    assert detect_language("outcome:failure", default="ru") == "ru"  # control value, keep caller's
    assert detect_language("O'zbekistondan", default="uz") == "uz"
