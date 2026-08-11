"""Inactive official-link inventory and fail-closed runtime lookup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from app.domain.approved_links import ApprovedLinkEntry, LinkLanguage


class ApprovedLinkRegistry(Protocol):
    """Only server-owned identifiers may be resolved to a runtime URL."""

    def resolve_runtime(self, link_id: str, language: LinkLanguage) -> str | None:
        """Return an independently approved active URL or no URL."""
        ...


class InMemoryApprovedLinkRegistry:
    """Stage 3B registry whose seed entries are deliberately all inactive."""

    def __init__(self, entries: list[ApprovedLinkEntry]) -> None:
        self._entries = {entry.link_id: entry.model_copy(deep=True) for entry in entries}
        if len(self._entries) != len(entries):
            raise ValueError("link IDs must be unique")

    def entries(self) -> list[ApprovedLinkEntry]:
        return [entry.model_copy(deep=True) for entry in self._entries.values()]

    def resolve_runtime(self, link_id: str, language: LinkLanguage) -> str | None:
        entry = self._entries.get(link_id)
        if entry is None:
            return None
        language_matches = entry.language in {language, LinkLanguage.MULTILINGUAL}
        if not entry.active or not entry.runtime_eligible or not language_matches:
            return None
        return str(entry.url)


def stage3b_link_registry() -> InMemoryApprovedLinkRegistry:
    """Return the reviewed inventory, pending owner approval and inactive."""
    verified = datetime(2026, 8, 11, 0, tzinfo=UTC)
    review_due = datetime(2026, 9, 10, 0, tzinfo=UTC)
    rows = (
        ("rtmc_home", "https://rtmc.uz/", LinkLanguage.MULTILINGUAL, "RTMC home"),
        ("rtmc_contact", "https://rtmc.uz/contact", LinkLanguage.MULTILINGUAL, "RTMC contact"),
        ("rtmc_faq", "https://rtmc.uz/contact/faq", LinkLanguage.MULTILINGUAL, "RTMC FAQ"),
        (
            "rtmc_appeal",
            "https://rtmc.uz/contact/send-appeal",
            LinkLanguage.MULTILINGUAL,
            "Official appeal page reference",
        ),
        (
            "rtmc_phone_codes",
            "https://rtmc.uz/opendata/phone-codes",
            LinkLanguage.MULTILINGUAL,
            "Phone code open data",
        ),
        (
            "uzimei_instructions",
            "https://uzimei.uz/?id=instructions",
            LinkLanguage.UZ,
            "UZIMEI instructions",
        ),
        ("uzimei_knowledge", "https://uzimei.uz/knowledge", LinkLanguage.UZ, "UZIMEI knowledge"),
        ("uzimei_tariffs", "https://uzimei.uz/tariffs", LinkLanguage.UZ, "UZIMEI tariffs"),
        ("uzimei_contacts", "https://uzimei.uz/contacts", LinkLanguage.UZ, "UZIMEI contacts"),
        ("mnp_uz", "https://mnp.uz/", LinkLanguage.UZ, "MNP Uzbek page"),
        ("mnp_ru", "https://mnp.uz/ru", LinkLanguage.RU, "MNP Russian page"),
        ("mnp_en", "https://www.mnp.uz/en", LinkLanguage.EN, "MNP English page"),
        (
            "lex_3336169",
            "https://lex.uz/docs/3336169",
            LinkLanguage.MULTILINGUAL,
            "Legal source reference",
        ),
    )
    return InMemoryApprovedLinkRegistry(
        [
            ApprovedLinkEntry(
                link_id=link_id,
                url=url,
                language=language,
                purpose=purpose,
                owner="RTMC content owner (approval pending)",
                verified_at=verified,
                review_due_at=review_due,
            )
            for link_id, url, language, purpose in rows
        ]
    )
