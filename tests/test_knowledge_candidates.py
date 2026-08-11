"""Stage 2 candidate-package governance and privacy tests."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.governance import governed_content_hash
from app.domain.knowledge_candidates import CandidatePackage, KnowledgeCandidate
from app.services.knowledge_candidates import (
    CandidatePackageError,
    candidate_approval_failures,
    candidate_is_retrievable,
    candidate_retrieval_failures,
    load_candidate_package,
    validate_candidate_set,
)
from app.services.pii import DerivedFixturePIIError

NOW = datetime(2026, 8, 4, 12, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
UZBEK_PACKAGE = PROJECT_ROOT / "data/knowledge/candidates/uz/demo3_faq_candidates.json"
RUSSIAN_PACKAGE = PROJECT_ROOT / "data/knowledge/translations/ru/demo3_faq_translations.json"
ENGLISH_PACKAGE = PROJECT_ROOT / "data/knowledge/translations/en/demo3_faq_translations.json"


def candidate_values(*, language: str = "uz", suffix: str = "UZ") -> dict[str, object]:
    question = f"Synthetic {language} candidate question?"
    answer = f"Synthetic {language} candidate answer for review only."
    provenance: dict[str, object] | None = None
    reviewer_role: str | None = None
    if language != "uz":
        source_question = "Synthetic uz candidate question?"
        source_answer = "Synthetic uz candidate answer for review only."
        provenance = {
            "source_language": "uz",
            "source_record_id": "IMEI-UZ-SYNTHETIC-001",
            "source_version": 1,
            "source_content_sha256": governed_content_hash(
                question=source_question,
                answer=source_answer,
            ),
            "method": "machine_assisted_engineering_draft",
        }
        reviewer_role = f"Synthetic {language} reviewer"
    return {
        "record_id": f"IMEI-{suffix}-SYNTHETIC-001",
        "language": language,
        "category": "imei",
        "subcategory": "registration_general",
        "question": question,
        "question_variants": [question],
        "answer": answer,
        "answer_mode": "deterministic",
        "risk_level": "low",
        "source_document_id": "DEPT-TEST-001",
        "source_sha256": "1" * 64,
        "source_paragraphs": [1, 2],
        "official_sources": [
            {
                "url": "https://uzimei.uz/",
                "page_title": "Synthetic official source title",
                "retrieved_at": NOW.isoformat(),
                "section": "Synthetic section",
                "outcome": "supports",
                "note": "Synthetic evidence for validation only.",
            }
        ],
        "content_sha256": governed_content_hash(question=question, answer=answer),
        "content_owner_role": "Synthetic content owner",
        "content_owner_name": None,
        "legal_reviewer_role": None,
        "legal_reviewer_name": None,
        "translation_reviewer_role": reviewer_role,
        "translation_reviewer_name": None,
        "sensitivity": "public_candidate",
        "time_sensitive": False,
        "valid_from": None,
        "valid_until": None,
        "review_due_at": (NOW + timedelta(days=30)).isoformat(),
        "last_verified_at": NOW.isoformat(),
        "verification_status": "verified",
        "conflict_status": "clear",
        "approval_status": "pending_review",
        "activation_status": "inactive",
        "runtime_eligible": False,
        "quarantined": True,
        "synthetic": False,
        "approved_by": None,
        "approved_at": None,
        "translation_approved": False,
        "legal_summary_approved": False,
        "translation_provenance": provenance,
        "review_decision": None,
        "reviewer_name": None,
        "reviewer_position": None,
        "decision_timestamp": None,
        "reviewer_comments": None,
        "version": 1,
    }


def package_values(record: dict[str, object], *, language: str) -> dict[str, object]:
    return {
        "package_version": 1,
        "stage": "demo3_stage2",
        "language": language,
        "source_document_id": "DEPT-TEST-001",
        "source_sha256": "1" * 64,
        "generated_at": NOW.isoformat(),
        "records": [record],
    }


def write_package(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_pending_inactive_candidate_is_never_retrievable() -> None:
    candidate = KnowledgeCandidate.model_validate(candidate_values())

    assert not candidate_is_retrievable(candidate)
    assert set(candidate_retrieval_failures(candidate)) >= {
        "candidate_not_approved",
        "candidate_not_active",
        "candidate_quarantined",
        "candidate_runtime_ineligible",
    }


def test_content_hash_and_source_references_fail_closed() -> None:
    bad_hash = candidate_values()
    bad_hash["content_sha256"] = "0" * 64
    missing_reference = candidate_values()
    missing_reference["source_paragraphs"] = []

    with pytest.raises(ValidationError, match="content hash mismatch"):
        KnowledgeCandidate.model_validate(bad_hash)
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate(missing_reference)


def test_candidate_cannot_skip_directly_to_approved_or_active() -> None:
    approved = candidate_values()
    approved["approval_status"] = "approved"
    active = candidate_values()
    active["activation_status"] = "active"
    active["runtime_eligible"] = True
    active["quarantined"] = False

    with pytest.raises(ValidationError, match="pending review"):
        KnowledgeCandidate.model_validate(approved)
    with pytest.raises(ValidationError, match="inactive"):
        KnowledgeCandidate.model_validate(active)


def test_missing_human_ownership_blocks_approval_eligibility() -> None:
    candidate = KnowledgeCandidate.model_validate(candidate_values())

    assert set(candidate_approval_failures(candidate)) >= {
        "content_owner_missing",
        "review_decision_missing",
    }


def test_duplicate_ids_and_duplicate_questions_are_rejected() -> None:
    first = candidate_values()
    duplicate_id = deepcopy(first)
    duplicate_id["question"] = "A different synthetic question?"
    duplicate_id["question_variants"] = [duplicate_id["question"]]
    duplicate_id["answer"] = "A different synthetic answer."
    duplicate_id["content_sha256"] = governed_content_hash(
        question=str(duplicate_id["question"]),
        answer=str(duplicate_id["answer"]),
    )
    values = package_values(first, language="uz")
    values["records"] = [first, duplicate_id]

    with pytest.raises(ValidationError, match="record IDs must be unique"):
        CandidatePackage.model_validate(values)

    duplicate_question = deepcopy(first)
    duplicate_question["record_id"] = "IMEI-UZ-SYNTHETIC-002"
    values["records"] = [first, duplicate_question]
    with pytest.raises(ValidationError, match="duplicate candidate questions"):
        CandidatePackage.model_validate(values)


def test_raw_fields_and_unauthorized_sources_are_rejected(tmp_path: Path) -> None:
    raw = candidate_values()
    raw["raw_text"] = "synthetic raw content"
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate(raw)

    unauthorized = candidate_values()
    sources = unauthorized["official_sources"]
    assert isinstance(sources, list)
    sources[0]["url"] = "https://example.invalid/source"
    path = tmp_path / "unauthorized.json"
    write_package(path, package_values(unauthorized, language="uz"))
    with pytest.raises(CandidatePackageError, match="unauthorized_source"):
        load_candidate_package(path)


def test_pii_in_candidate_artifact_is_rejected(tmp_path: Path) -> None:
    values = candidate_values()
    values["answer"] = "Synthetic contact: +998 90 123 45 67"
    values["content_sha256"] = governed_content_hash(
        question=str(values["question"]),
        answer=str(values["answer"]),
    )
    path = tmp_path / "pii.json"
    write_package(path, package_values(values, language="uz"))

    with pytest.raises(DerivedFixturePIIError):
        load_candidate_package(path)


def test_translation_linkage_and_approval_remain_independent(tmp_path: Path) -> None:
    uz = candidate_values()
    ru = candidate_values(language="ru", suffix="RU")
    en = candidate_values(language="en", suffix="EN")
    paths = {language: tmp_path / f"{language}.json" for language in ("uz", "ru", "en")}
    write_package(paths["uz"], package_values(uz, language="uz"))
    write_package(paths["ru"], package_values(ru, language="ru"))
    write_package(paths["en"], package_values(en, language="en"))

    report = validate_candidate_set(
        uzbek_path=paths["uz"],
        russian_path=paths["ru"],
        english_path=paths["en"],
    )

    assert report.uzbek_records == report.russian_records == report.english_records == 1
    assert report.runtime_eligible_records == 0
    russian = load_candidate_package(paths["ru"]).records[0]
    english = load_candidate_package(paths["en"]).records[0]
    assert not candidate_is_retrievable(russian)
    assert not candidate_is_retrievable(english)
    assert "translation_not_approved" in candidate_retrieval_failures(russian)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("source_content_sha256", "2" * 64), ("source_version", 2)],
)
def test_translation_hash_or_version_mismatch_is_rejected(
    tmp_path: Path,
    field: str,
    bad_value: object,
) -> None:
    uz = candidate_values()
    ru = candidate_values(language="ru", suffix="RU")
    en = candidate_values(language="en", suffix="EN")
    provenance = ru["translation_provenance"]
    assert isinstance(provenance, dict)
    provenance[field] = bad_value
    paths = {language: tmp_path / f"{language}.json" for language in ("uz", "ru", "en")}
    write_package(paths["uz"], package_values(uz, language="uz"))
    write_package(paths["ru"], package_values(ru, language="ru"))
    write_package(paths["en"], package_values(en, language="en"))

    with pytest.raises(CandidatePackageError, match="translation_source_mismatch"):
        validate_candidate_set(
            uzbek_path=paths["uz"],
            russian_path=paths["ru"],
            english_path=paths["en"],
        )


def test_demo3_candidate_artifacts_are_complete_and_runtime_ineligible() -> None:
    report = validate_candidate_set(
        uzbek_path=UZBEK_PACKAGE,
        russian_path=RUSSIAN_PACKAGE,
        english_path=ENGLISH_PACKAGE,
    )
    packages = [
        load_candidate_package(UZBEK_PACKAGE),
        load_candidate_package(RUSSIAN_PACKAGE),
        load_candidate_package(ENGLISH_PACKAGE),
    ]

    assert report.uzbek_records == report.russian_records == report.english_records == 46
    assert report.runtime_eligible_records == 0
    assert all(
        not candidate_is_retrievable(record) for package in packages for record in package.records
    )
    assert all(record.approved_by is None for package in packages for record in package.records)


def test_conflicted_source_items_are_absent_from_candidate_packages() -> None:
    conflicts = json.loads(
        (PROJECT_ROOT / "reports/demo3_stage2_conflicts.json").read_text(encoding="utf-8")
    )
    candidate_ids = {
        record.record_id
        for package_path in (UZBEK_PACKAGE, RUSSIAN_PACKAGE, ENGLISH_PACKAGE)
        for record in load_candidate_package(package_path).records
    }

    assert len(conflicts["conflicts"]) == 4
    assert all(conflict["status"] == "unresolved" for conflict in conflicts["conflicts"])
    assert all(
        conflict["provisional_record_id"] not in candidate_ids
        for conflict in conflicts["conflicts"]
    )


def test_knowledge_tree_contains_only_normalized_json_artifacts() -> None:
    knowledge_root = PROJECT_ROOT / "data/knowledge"
    files = [path for path in knowledge_root.rglob("*") if path.is_file()]

    assert files
    assert all(path.suffix == ".json" for path in files)
    assert all("MNP va IMEI FAQ.docx" not in path.read_text(encoding="utf-8") for path in files)
