"""Source-integrity, offline extraction, and archive-safety tests."""

from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.governance import SourceClassification, SourceManifestEntry
from app.services.confidential_sources import (
    ArchiveMember,
    ConfidentialSourceError,
    OfflineExtractionPolicy,
    SourceHashMismatchError,
    UnsafeArchiveError,
    extract_zip_safely,
    inspect_archive_members,
    inspect_zip_archive,
    run_local_extraction,
    verify_manifest_entry,
)
from app.services.source_manifest import create_local_pdf_manifest


class SyntheticLocalExtractor:
    """Network-free test double; it never handles departmental content."""

    def __init__(self) -> None:
        self.called = False

    def extract_text(self, source: Path, *, policy: OfflineExtractionPolicy) -> str:
        self.called = True
        assert policy.network_access is False
        return source.read_text(encoding="utf-8")


def manifest_entry(filename: str, digest: str) -> SourceManifestEntry:
    return SourceManifestEntry(
        source_id="CONF-TEST-001",
        filename=filename,
        sha256=digest,
        classification=SourceClassification.CONFIDENTIAL_CASE,
    )


def test_manifest_hash_verification_succeeds_without_returning_content(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic non-personal bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    result = verify_manifest_entry(manifest_entry(source.name, digest), source_root=tmp_path)

    assert result.source_id == "CONF-TEST-001"
    assert result.observed_sha256 == digest
    assert result.matches is True
    assert "synthetic non-personal bytes" not in repr(result)


def test_manifest_hash_mismatch_fails_with_source_id_only(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic bytes")

    with pytest.raises(SourceHashMismatchError, match="CONF-TEST-001") as error:
        verify_manifest_entry(manifest_entry(source.name, "0" * 64), source_root=tmp_path)

    assert "synthetic bytes" not in str(error.value)


@pytest.mark.parametrize("filename", ["../source.pdf", "/source.pdf", "nested/source.pdf"])
def test_manifest_rejects_nonlocal_filenames(filename: str) -> None:
    with pytest.raises(ValidationError):
        manifest_entry(filename, "0" * 64)


def test_manifest_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.pdf"
    target.write_bytes(b"synthetic")
    link = tmp_path / "link.pdf"
    link.symlink_to(target)

    with pytest.raises(ConfidentialSourceError, match="source_not_regular_file"):
        verify_manifest_entry(
            manifest_entry(link.name, hashlib.sha256(b"synthetic").hexdigest()),
            source_root=tmp_path,
        )


def test_manifest_rejects_overly_open_source_root(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    tmp_path.chmod(0o755)

    with pytest.raises(ConfidentialSourceError, match="source_root_permissions_too_open"):
        verify_manifest_entry(
            manifest_entry(source.name, hashlib.sha256(b"synthetic").hexdigest()),
            source_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("path", "expected_code"),
    [
        ("../escape.pdf", "archive_path_traversal"),
        ("nested\\escape.pdf", "archive_path_traversal"),
        ("payload.exe", "archive_executable_rejected"),
        ("template.docm", "archive_macro_rejected"),
        ("nested.zip", "nested_archive_rejected"),
        ("unexpected.csv", "archive_type_not_allowed"),
    ],
)
def test_archive_policy_rejects_unsafe_paths_and_types(path: str, expected_code: str) -> None:
    member = ArchiveMember(path, False, False, False, 10, 5)

    with pytest.raises(UnsafeArchiveError, match=expected_code):
        inspect_archive_members([member], policy=OfflineExtractionPolicy())


def test_archive_policy_rejects_symlink_and_excessive_ratio() -> None:
    symlink = ArchiveMember("safe.pdf", False, True, False, 10, 5)
    bomb = ArchiveMember("safe.pdf", False, False, False, 10_000, 1)

    with pytest.raises(UnsafeArchiveError, match="archive_symlink_rejected"):
        inspect_archive_members([symlink], policy=OfflineExtractionPolicy())
    with pytest.raises(UnsafeArchiveError, match="archive_compression_ratio_exceeded"):
        inspect_archive_members([bomb], policy=OfflineExtractionPolicy())


def test_zip_symlink_is_rejected_before_extraction(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    info = zipfile.ZipInfo("linked.pdf")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target.pdf")

    with pytest.raises(UnsafeArchiveError, match="archive_symlink_rejected"):
        inspect_zip_archive(archive_path, policy=OfflineExtractionPolicy())


def test_zip_extracts_only_inspected_synthetic_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "safe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("folder/synthetic.txt", "privacy-safe synthetic text")

    destination = tmp_path / "output"
    extracted = extract_zip_safely(
        archive_path,
        destination=destination,
        policy=OfflineExtractionPolicy(),
    )

    assert extracted == (destination / "folder" / "synthetic.txt",)
    assert extracted[0].read_text(encoding="utf-8") == "privacy-safe synthetic text"


def test_extraction_policy_cannot_enable_network() -> None:
    with pytest.raises(ValidationError):
        OfflineExtractionPolicy(network_access=True)


def test_local_extractor_receives_offline_policy(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.txt"
    source.write_text("privacy-safe synthetic text", encoding="utf-8")
    extractor = SyntheticLocalExtractor()

    result = run_local_extraction(
        source,
        extractor=extractor,
        policy=OfflineExtractionPolicy(),
    )

    assert extractor.called is True
    assert result == "privacy-safe synthetic text"


def test_local_pdf_manifest_is_mode_600_and_contains_hashes_only(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"privacy-safe synthetic bytes")
    output = tmp_path / "pdf-sha256-manifest.json"

    count = create_local_pdf_manifest(source_root=tmp_path, output=output)

    assert count == 1
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    manifest_text = output.read_text(encoding="utf-8")
    assert "synthetic.pdf" in manifest_text
    assert hashlib.sha256(source.read_bytes()).hexdigest() in manifest_text
    assert "privacy-safe synthetic bytes" not in manifest_text


def test_local_pdf_manifest_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "pdf-sha256-manifest.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(ConfidentialSourceError, match="output_must_be_new"):
        create_local_pdf_manifest(source_root=tmp_path, output=output)
