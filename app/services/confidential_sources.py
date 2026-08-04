"""Offline, fail-closed safeguards for confidential source transformation."""

from __future__ import annotations

import hashlib
import hmac
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import Field

from app.domain.governance import SourceManifest, SourceManifestEntry
from app.domain.schemas import StrictModel

SOURCE_SUFFIXES = frozenset({".doc", ".docx", ".pdf", ".rar"})
DEFAULT_EXTRACTED_SUFFIXES = frozenset({".doc", ".docx", ".pdf", ".txt"})
EXECUTABLE_SUFFIXES = frozenset(
    {
        ".app",
        ".bat",
        ".bin",
        ".cmd",
        ".com",
        ".dll",
        ".dmg",
        ".exe",
        ".jar",
        ".js",
        ".msi",
        ".ps1",
        ".scr",
        ".sh",
    }
)
MACRO_SUFFIXES = frozenset({".docm", ".dotm", ".ppam", ".pptm", ".xlam", ".xlsm"})
ARCHIVE_SUFFIXES = frozenset({".7z", ".gz", ".rar", ".tar", ".tgz", ".zip"})


class ConfidentialSourceError(ValueError):
    """Safe policy error that never includes extracted or personal content."""


class SourceHashMismatchError(ConfidentialSourceError):
    """The local file differs from its reviewed manifest digest."""


class UnsafeArchiveError(ConfidentialSourceError):
    """An archive cannot be inspected or extracted under the approved policy."""


class OfflineExtractionPolicy(StrictModel):
    """Extraction is local-only; network access cannot be enabled by configuration."""

    network_access: Literal[False] = False
    allowed_suffixes: frozenset[str] = Field(default=DEFAULT_EXTRACTED_SUFFIXES)
    max_files: int = Field(default=250, ge=1, le=10_000)
    max_file_bytes: int = Field(default=25_000_000, ge=1)
    max_total_bytes: int = Field(default=100_000_000, ge=1)
    max_compression_ratio: float = Field(default=100.0, ge=1, le=10_000)


class LocalTextExtractor(Protocol):
    """Stage 2 seam for a local document/PDF extractor with no network capability."""

    def extract_text(self, source: Path, *, policy: OfflineExtractionPolicy) -> str:
        """Extract locally and return text for immediate privacy validation."""
        ...


@dataclass(frozen=True, slots=True)
class HashVerification:
    """Content-free digest result safe for audit output."""

    source_id: str
    observed_sha256: str
    matches: bool


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    """Content-free member metadata used by archive safety policy."""

    path: str
    is_directory: bool
    is_symlink: bool
    encrypted: bool
    uncompressed_size: int
    compressed_size: int


def sha256_file(path: Path) -> str:
    """Hash a regular, non-symlink file without loading it into memory."""
    if path.is_symlink() or not path.is_file():
        raise ConfidentialSourceError("source_not_regular_file")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest_entry(entry: SourceManifestEntry, *, source_root: Path) -> HashVerification:
    """Verify one quarantined source selected only by a safe manifest filename."""
    root = source_root.resolve(strict=True)
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise ConfidentialSourceError("source_root_permissions_too_open")
    candidate = root / entry.filename
    if candidate.parent.resolve(strict=True) != root:
        raise ConfidentialSourceError(f"source_path_outside_root:{entry.source_id}")
    if candidate.suffix.casefold() not in SOURCE_SUFFIXES:
        raise ConfidentialSourceError(f"source_type_not_allowed:{entry.source_id}")
    observed = sha256_file(candidate)
    matches = hmac.compare_digest(observed, entry.sha256)
    if not matches:
        raise SourceHashMismatchError(f"source_hash_mismatch:{entry.source_id}")
    return HashVerification(entry.source_id, observed, matches)


def verify_manifest(manifest: SourceManifest, *, source_root: Path) -> list[HashVerification]:
    """Verify every entry and fail closed on the first missing or mismatched source."""
    return [verify_manifest_entry(entry, source_root=source_root) for entry in manifest.entries]


def inspect_archive_members(
    members: list[ArchiveMember],
    *,
    policy: OfflineExtractionPolicy,
) -> tuple[ArchiveMember, ...]:
    """Reject traversal, links, active content, nesting, and archive bombs."""
    if len(members) > policy.max_files:
        raise UnsafeArchiveError("archive_member_limit_exceeded")

    accepted: list[ArchiveMember] = []
    seen_paths: set[str] = set()
    total_size = 0
    for member in members:
        normalized = _safe_member_path(member.path)
        if normalized in seen_paths:
            raise UnsafeArchiveError("archive_duplicate_path")
        seen_paths.add(normalized)
        if member.is_symlink:
            raise UnsafeArchiveError("archive_symlink_rejected")
        if member.encrypted:
            raise UnsafeArchiveError("archive_encryption_rejected")
        if member.uncompressed_size < 0 or member.compressed_size < 0:
            raise UnsafeArchiveError("archive_negative_size")
        if member.is_directory:
            accepted.append(member)
            continue

        suffix = PurePosixPath(normalized).suffix.casefold()
        if suffix in EXECUTABLE_SUFFIXES:
            raise UnsafeArchiveError("archive_executable_rejected")
        if suffix in MACRO_SUFFIXES:
            raise UnsafeArchiveError("archive_macro_rejected")
        if suffix in ARCHIVE_SUFFIXES:
            raise UnsafeArchiveError("nested_archive_rejected")
        if suffix not in policy.allowed_suffixes:
            raise UnsafeArchiveError("archive_type_not_allowed")
        if member.uncompressed_size > policy.max_file_bytes:
            raise UnsafeArchiveError("archive_file_size_limit_exceeded")
        total_size += member.uncompressed_size
        if total_size > policy.max_total_bytes:
            raise UnsafeArchiveError("archive_total_size_limit_exceeded")
        if member.compressed_size == 0:
            if member.uncompressed_size > 0:
                raise UnsafeArchiveError("archive_compression_ratio_exceeded")
        elif member.uncompressed_size / member.compressed_size > policy.max_compression_ratio:
            raise UnsafeArchiveError("archive_compression_ratio_exceeded")
        accepted.append(member)
    return tuple(accepted)


def inspect_zip_archive(
    archive_path: Path,
    *,
    policy: OfflineExtractionPolicy,
) -> tuple[ArchiveMember, ...]:
    """Read ZIP metadata only and apply the shared archive policy."""
    if archive_path.is_symlink() or not archive_path.is_file():
        raise UnsafeArchiveError("archive_not_regular_file")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [_zip_member(info) for info in archive.infolist()]
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise UnsafeArchiveError("archive_invalid") from exc
    return inspect_archive_members(members, policy=policy)


def extract_zip_safely(
    archive_path: Path,
    *,
    destination: Path,
    policy: OfflineExtractionPolicy,
) -> tuple[Path, ...]:
    """Extract an inspected ZIP without links, overwrites, or path escapes."""
    members = inspect_zip_archive(archive_path, policy=policy)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.is_symlink() or any(destination.iterdir()):
        raise UnsafeArchiveError("extraction_destination_not_empty")
    root = destination.resolve(strict=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        infos = {info.filename: info for info in archive.infolist()}
        for member in members:
            relative = Path(*PurePosixPath(member.path).parts)
            target = root / relative
            if target.parent.resolve(strict=False) != root and root not in target.parents:
                raise UnsafeArchiveError("archive_path_traversal")
            if member.is_directory:
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                with archive.open(infos[member.path]) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            except (KeyError, OSError, RuntimeError) as exc:
                raise UnsafeArchiveError("archive_extraction_failed") from exc
            if target.stat().st_size != member.uncompressed_size:
                raise UnsafeArchiveError("archive_extracted_size_mismatch")
            extracted.append(target)
    return tuple(extracted)


def run_local_extraction(
    source: Path,
    *,
    extractor: LocalTextExtractor,
    policy: OfflineExtractionPolicy,
) -> str:
    """Invoke only an injected local extractor after enforcing the offline boundary."""
    if policy.network_access is not False:
        raise ConfidentialSourceError("network_access_forbidden")
    if source.is_symlink() or not source.is_file():
        raise ConfidentialSourceError("source_not_regular_file")
    if source.suffix.casefold() not in policy.allowed_suffixes:
        raise ConfidentialSourceError("extraction_type_not_allowed")
    return extractor.extract_text(source, policy=policy)


def _safe_member_path(value: str) -> str:
    if not value or "\\" in value or value.startswith("/"):
        raise UnsafeArchiveError("archive_path_traversal")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeArchiveError("archive_path_traversal")
    if len(path.parts) > 32 or (path.parts and ":" in path.parts[0]):
        raise UnsafeArchiveError("archive_path_invalid")
    return path.as_posix()


def _zip_member(info: zipfile.ZipInfo) -> ArchiveMember:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    is_symlink = stat.S_ISLNK(unix_mode)
    return ArchiveMember(
        path=info.filename,
        is_directory=info.is_dir(),
        is_symlink=is_symlink,
        encrypted=bool(info.flag_bits & 0x1),
        uncompressed_size=info.file_size,
        compressed_size=info.compress_size,
    )
