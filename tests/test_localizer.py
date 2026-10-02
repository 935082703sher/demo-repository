"""UI-string localizer: translate nav labels, with the originals as the safety net."""

from __future__ import annotations

import asyncio

from app.services.localizer import LLMLocalizer, TemplateLocalizer

_LABELS = ["Qurilma bloklangan", "MNP arizasi rad etildi"]


def _run(localizer: LLMLocalizer | TemplateLocalizer, labels: list[str]) -> list[str]:
    return asyncio.run(localizer.localize(labels, "kaa"))


def test_template_returns_labels_unchanged() -> None:
    assert _run(TemplateLocalizer(), _LABELS) == _LABELS


def test_empty_list_needs_no_call() -> None:
    async def boom(prompt: str) -> str:  # must never be awaited
        raise AssertionError("should not call the model for an empty list")

    assert _run(LLMLocalizer(boom, fallback=TemplateLocalizer()), []) == []


def test_llm_uses_translated_labels() -> None:
    async def fake(prompt: str) -> str:
        return '{"texts": ["Qurılma bloklanǵan", "MNP arzası biykarlandı"]}'

    out = _run(LLMLocalizer(fake, fallback=TemplateLocalizer()), _LABELS)
    assert out == ["Qurılma bloklanǵan", "MNP arzası biykarlandı"]


def test_llm_falls_back_on_error() -> None:
    async def broken(prompt: str) -> str:
        raise RuntimeError("network down")

    out = _run(LLMLocalizer(broken, fallback=TemplateLocalizer()), _LABELS)
    assert out == _LABELS


def test_llm_falls_back_on_count_mismatch() -> None:
    async def wrong_count(prompt: str) -> str:
        return '{"texts": ["only one"]}'  # two were asked for

    out = _run(LLMLocalizer(wrong_count, fallback=TemplateLocalizer()), _LABELS)
    assert out == _LABELS  # a shape mismatch is dropped in favour of the originals
