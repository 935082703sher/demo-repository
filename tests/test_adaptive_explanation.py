"""Adaptive explanation: style from the customer's words, escalation on confusion."""

from __future__ import annotations

from app.domain.case_state import ExplanationStyle
from app.services.explanation import detect_style, reexplain_leadin, style_for_confusion


def test_detect_style_from_cues() -> None:
    assert detect_style("qisqa ayting") is ExplanationStyle.CONCISE
    assert detect_style("tushunmadim") is ExplanationStyle.SIMPLE
    assert detect_style("qayerni bosaman?") is ExplanationStyle.STEP_BY_STEP
    assert detect_style("misol bilan tushuntiring") is ExplanationStyle.EXAMPLE
    assert detect_style("nega bunday bo'ldi?") is ExplanationStyle.DETAILED
    assert detect_style("skrinshot yuboraman") is ExplanationStyle.VISUAL
    assert detect_style("juda xavotirdaman") is ExplanationStyle.REASSURING


def test_detect_style_none_for_plain_message() -> None:
    assert detect_style("telefonim royxatdan otmayapti") is None


def test_confusion_escalates_the_style() -> None:
    assert style_for_confusion(1) is ExplanationStyle.SIMPLE
    assert style_for_confusion(2) is ExplanationStyle.STEP_BY_STEP
    assert style_for_confusion(3) is ExplanationStyle.EXAMPLE
    assert style_for_confusion(5) is ExplanationStyle.EXAMPLE


def test_reexplain_leadins_differ_per_level_so_text_is_never_repeated() -> None:
    first = reexplain_leadin(style_for_confusion(1), "uz")
    second = reexplain_leadin(style_for_confusion(2), "uz")
    third = reexplain_leadin(style_for_confusion(3), "uz")
    assert len({first, second, third}) == 3  # each re-explanation opens differently


def test_reexplain_leadin_localized() -> None:
    assert reexplain_leadin(ExplanationStyle.SIMPLE, "ru") != reexplain_leadin(
        ExplanationStyle.SIMPLE, "en"
    )
    # Unknown language falls back to Uzbek, never crashes.
    assert reexplain_leadin(ExplanationStyle.SIMPLE, "xx")
