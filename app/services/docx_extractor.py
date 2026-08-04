"""Hardened, network-free DOCX inspection and in-memory text extraction."""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from app.services.confidential_sources import (
    ArchiveMember,
    ConfidentialSourceError,
    OfflineExtractionPolicy,
    UnsafeArchiveError,
    inspect_archive_members,
)

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_PREFIXES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/",
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/",
)
_ALLOWED_RELATIONSHIP_KINDS = frozenset(
    {
        "comments",
        "core-properties",
        "custom-properties",
        "endnotes",
        "extended-properties",
        "fontTable",
        "footer",
        "footnotes",
        "header",
        "hyperlink",
        "image",
        "numbering",
        "officeDocument",
        "settings",
        "styles",
        "theme",
        "webSettings",
    }
)
_ALLOWED_PART_SUFFIXES = frozenset(
    {"", ".xml", ".rels", ".png", ".jpg", ".jpeg", ".gif", ".emf", ".wmf"}
)
_FORBIDDEN_PART_FRAGMENTS = (
    "/embeddings/",
    "/activeX/",
    "vbaProject",
    "attachedToolbars",
)
_FORBIDDEN_XML_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")


class UnsafeDocxError(ConfidentialSourceError):
    """The DOCX package violates the local extraction policy."""


@dataclass(frozen=True, slots=True)
class ExtractedParagraph:
    """One normalized paragraph with a stable source-order reference."""

    index: int
    text: str
    style: str | None


@dataclass(frozen=True, slots=True)
class DocxExtraction:
    """In-memory extraction result containing no temporary raw output path."""

    paragraphs: tuple[ExtractedParagraph, ...]
    part_count: int
    relationship_count: int


class SafeDocxExtractor:
    """Inspect DOCX structure and extract text without macros, OLE, or network."""

    def extract(self, source: Path, *, policy: OfflineExtractionPolicy) -> DocxExtraction:
        """Validate the complete package before reading normalized paragraph text."""
        if policy.network_access is not False:
            raise UnsafeDocxError("docx_network_access_forbidden")
        if source.suffix.casefold() != ".docx" or source.is_symlink() or not source.is_file():
            raise UnsafeDocxError("docx_source_invalid")
        try:
            with zipfile.ZipFile(source) as package:
                infos = package.infolist()
                members = [_member(info) for info in infos]
                docx_policy = policy.model_copy(update={"allowed_suffixes": _ALLOWED_PART_SUFFIXES})
                inspect_archive_members(members, policy=docx_policy)
                names = {info.filename for info in infos}
                _validate_required_parts(names)
                _validate_part_names(names)
                _validate_content_types(package)
                relationship_count = _validate_relationships(package, names)
                document = _read_xml(package, "word/document.xml", policy.max_file_bytes)
                _reject_unsafe_document_elements(document)
                paragraphs = _extract_paragraphs(document)
        except UnsafeArchiveError as exc:
            raise UnsafeDocxError("docx_package_unsafe") from exc
        except (OSError, KeyError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise UnsafeDocxError("docx_package_malformed") from exc
        if not paragraphs:
            raise UnsafeDocxError("docx_contains_no_text")
        return DocxExtraction(paragraphs, len(members), relationship_count)

    def extract_text(self, source: Path, *, policy: OfflineExtractionPolicy) -> str:
        """Implement the local text-extractor protocol without writing raw output."""
        return "\n".join(
            paragraph.text for paragraph in self.extract(source, policy=policy).paragraphs
        )


def _member(info: zipfile.ZipInfo) -> ArchiveMember:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    return ArchiveMember(
        path=info.filename,
        is_directory=info.is_dir(),
        is_symlink=(unix_mode & 0o170000) == 0o120000,
        encrypted=bool(info.flag_bits & 0x1),
        uncompressed_size=info.file_size,
        compressed_size=info.compress_size,
    )


def _validate_required_parts(names: set[str]) -> None:
    required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
    if not required.issubset(names):
        raise UnsafeDocxError("docx_required_part_missing")


def _validate_part_names(names: set[str]) -> None:
    for name in names:
        folded = f"/{name}".casefold()
        if any(fragment.casefold() in folded for fragment in _FORBIDDEN_PART_FRAGMENTS):
            raise UnsafeDocxError("docx_embedded_or_active_content_rejected")
        suffix = _part_suffix(name)
        if not name.endswith("/") and suffix not in _ALLOWED_PART_SUFFIXES:
            raise UnsafeDocxError("docx_part_type_not_allowed")
        if not name.endswith("/") and not suffix:
            raise UnsafeDocxError("docx_part_type_not_allowed")


def _validate_content_types(package: zipfile.ZipFile) -> None:
    root = _read_xml(package, "[Content_Types].xml", 1_000_000)
    if root.tag != f"{{{_CONTENT_NS}}}Types":
        raise UnsafeDocxError("docx_content_types_invalid")
    for element in root:
        content_type = element.attrib.get("ContentType", "").casefold()
        if any(
            marker in content_type for marker in ("macroenabled", "vba", "activex", "oleobject")
        ):
            raise UnsafeDocxError("docx_macro_or_active_content_rejected")


def _part_suffix(name: str) -> str:
    return ".rels" if PurePosixPath(name).name == ".rels" else PurePosixPath(name).suffix.casefold()


def _validate_relationships(package: zipfile.ZipFile, names: set[str]) -> int:
    count = 0
    for rels_name in sorted(name for name in names if name.endswith(".rels")):
        root = _read_xml(package, rels_name, 1_000_000)
        if root.tag != f"{{{_REL_NS}}}Relationships":
            raise UnsafeDocxError("docx_relationships_invalid")
        source_part = _relationship_source_part(rels_name)
        for relationship in root:
            count += 1
            relationship_type = relationship.attrib.get("Type", "")
            kind = relationship_type.rsplit("/", 1)[-1]
            if (
                not relationship_type.startswith(_REL_PREFIXES)
                or kind not in _ALLOWED_RELATIONSHIP_KINDS
            ):
                raise UnsafeDocxError("docx_relationship_type_not_allowed")
            target = relationship.attrib.get("Target")
            if not target:
                raise UnsafeDocxError("docx_relationship_target_missing")
            if relationship.attrib.get("TargetMode") == "External":
                if kind != "hyperlink" or not target.casefold().startswith(("https://", "http://")):
                    raise UnsafeDocxError("docx_external_relationship_rejected")
                continue
            resolved = _resolve_relationship_target(source_part, target)
            if resolved not in names:
                raise UnsafeDocxError("docx_relationship_target_missing")
    return count


def _relationship_source_part(rels_name: str) -> str:
    path = PurePosixPath(rels_name)
    if rels_name == "_rels/.rels":
        return ""
    if path.parent.name != "_rels" or not path.name.endswith(".rels"):
        raise UnsafeDocxError("docx_relationship_path_invalid")
    source_name = path.name[: -len(".rels")]
    return (path.parent.parent / source_name).as_posix()


def _resolve_relationship_target(source_part: str, target: str) -> str:
    if "\\" in target or target.startswith("/"):
        raise UnsafeDocxError("docx_relationship_path_invalid")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))
    if resolved == ".." or resolved.startswith("../") or ":" in resolved.split("/", 1)[0]:
        raise UnsafeDocxError("docx_relationship_path_invalid")
    return resolved


def _read_xml(package: zipfile.ZipFile, name: str, max_bytes: int) -> ElementTree.Element:
    try:
        data = package.read(name)
    except (KeyError, OSError, RuntimeError) as exc:
        raise UnsafeDocxError("docx_xml_part_unreadable") from exc
    if len(data) > max_bytes or any(marker in data.upper() for marker in _FORBIDDEN_XML_MARKERS):
        raise UnsafeDocxError("docx_xml_part_unsafe")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise UnsafeDocxError("docx_xml_malformed") from exc


def _reject_unsafe_document_elements(document: ElementTree.Element) -> None:
    forbidden_local_names = {"altChunk", "object", "OLEObject"}
    for element in document.iter():
        local_name = element.tag.rsplit("}", 1)[-1]
        if local_name in forbidden_local_names:
            raise UnsafeDocxError("docx_embedded_or_active_content_rejected")


def _extract_paragraphs(document: ElementTree.Element) -> tuple[ExtractedParagraph, ...]:
    paragraphs: list[ExtractedParagraph] = []
    for paragraph in document.iter(f"{{{_WORD_NS}}}p"):
        chunks: list[str] = []
        for element in paragraph.iter():
            if element.tag == f"{{{_WORD_NS}}}t" and element.text:
                chunks.append(element.text)
            elif element.tag == f"{{{_WORD_NS}}}tab":
                chunks.append("\t")
            elif element.tag in {f"{{{_WORD_NS}}}br", f"{{{_WORD_NS}}}cr"}:
                chunks.append("\n")
        text = " ".join("".join(chunks).split())
        if not text:
            continue
        style_element = paragraph.find(f"./{{{_WORD_NS}}}pPr/{{{_WORD_NS}}}pStyle")
        style = None
        if style_element is not None:
            style = style_element.attrib.get(f"{{{_WORD_NS}}}val")
        paragraphs.append(ExtractedParagraph(len(paragraphs) + 1, text, style))
    return tuple(paragraphs)
