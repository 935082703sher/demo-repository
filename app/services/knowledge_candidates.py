"""Validation boundary for Stage 2 candidate and translation packages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.domain.enums import Language
from app.domain.knowledge_candidates import CandidatePackage, KnowledgeCandidate
from app.services.pii import validate_derived_fixture

_AUTHORIZED_SOURCE_HOSTS = frozenset(
    {
        "customs.uz",
        "lex.uz",
        "mnp.uz",
        "my.gov.uz",
        "rtmc.uz",
        "uzimei.customs.uz",
        "uzimei.uz",
        "www.customs.uz",
        "www.lex.uz",
        "www.mnp.uz",
        "www.rtmc.uz",
        "www.uzimei.uz",
    }
)


class CandidatePackageError(ValueError):
    """A candidate set cannot safely proceed to human review."""


@dataclass(frozen=True, slots=True)
class CandidateSetReport:
    """Content-free validation result suitable for completion evidence."""

    uzbek_records: int
    russian_records: int
    english_records: int
    runtime_eligible_records: int


def load_candidate_package(path: Path) -> CandidatePackage:
    """Validate JSON, PII policy, authorized sources, and strict record state."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    validate_derived_fixture(value)
    package = CandidatePackage.model_validate(value)
    for record in package.records:
        for evidence in record.official_sources:
            if urlsplit(evidence.url).hostname not in _AUTHORIZED_SOURCE_HOSTS:
                raise CandidatePackageError("candidate_unauthorized_source")
    return package


def validate_candidate_set(
    *,
    uzbek_path: Path,
    russian_path: Path,
    english_path: Path,
) -> CandidateSetReport:
    """Require complete, independently inactive RU/EN drafts for every Uzbek record."""
    uzbek = load_candidate_package(uzbek_path)
    russian = load_candidate_package(russian_path)
    english = load_candidate_package(english_path)
    if (uzbek.language, russian.language, english.language) != (
        Language.UZ,
        Language.RU,
        Language.EN,
    ):
        raise CandidatePackageError("candidate_package_language_mismatch")

    source_by_id = {record.record_id: record for record in uzbek.records}
    _validate_translations(russian, source_by_id)
    _validate_translations(english, source_by_id)
    if len(russian.records) != len(uzbek.records) or len(english.records) != len(uzbek.records):
        raise CandidatePackageError("candidate_translation_count_mismatch")

    all_records = (*uzbek.records, *russian.records, *english.records)
    all_ids = [record.record_id for record in all_records]
    if len(all_ids) != len(set(all_ids)):
        raise CandidatePackageError("candidate_cross_package_duplicate_id")
    return CandidateSetReport(
        uzbek_records=len(uzbek.records),
        russian_records=len(russian.records),
        english_records=len(english.records),
        runtime_eligible_records=sum(record.runtime_eligible for record in all_records),
    )


def candidate_retrieval_failures(record: KnowledgeCandidate) -> tuple[str, ...]:
    """Explain why a Stage 2 candidate cannot enter runtime retrieval."""
    failures: list[str] = []
    if record.approval_status.value != "approved":
        failures.append("candidate_not_approved")
    if record.activation_status.value != "active":
        failures.append("candidate_not_active")
    if record.quarantined:
        failures.append("candidate_quarantined")
    if not record.runtime_eligible:
        failures.append("candidate_runtime_ineligible")
    if record.language is not Language.UZ and not record.translation_approved:
        failures.append("translation_not_approved")
    return tuple(failures)


def candidate_is_retrievable(record: KnowledgeCandidate) -> bool:
    """Stage 2 review packages are deliberately unavailable to the application."""
    return not candidate_retrieval_failures(record)


def candidate_approval_failures(record: KnowledgeCandidate) -> tuple[str, ...]:
    """Require named human owners and independent language/legal review."""
    failures: list[str] = []
    if record.content_owner_name is None:
        failures.append("content_owner_missing")
    if record.legal_reviewer_role and record.legal_reviewer_name is None:
        failures.append("legal_reviewer_missing")
    if record.language is not Language.UZ and record.translation_reviewer_name is None:
        failures.append("translation_reviewer_missing")
    if record.review_decision is None:
        failures.append("review_decision_missing")
    return tuple(failures)


def _validate_translations(
    package: CandidatePackage,
    source_by_id: dict[str, KnowledgeCandidate],
) -> None:
    seen_source_ids: set[str] = set()
    for translation in package.records:
        provenance = translation.translation_provenance
        if provenance is None:
            raise CandidatePackageError("candidate_translation_provenance_missing")
        source = source_by_id.get(provenance.source_record_id)
        if source is None:
            raise CandidatePackageError("candidate_translation_source_missing")
        if provenance.source_record_id in seen_source_ids:
            raise CandidatePackageError("candidate_duplicate_translation_source")
        seen_source_ids.add(provenance.source_record_id)
        if (
            provenance.source_version != source.version
            or provenance.source_content_sha256 != source.content_sha256
            or translation.category is not source.category
            or translation.subcategory != source.subcategory
            or translation.source_paragraphs != source.source_paragraphs
        ):
            raise CandidatePackageError("candidate_translation_source_mismatch")
