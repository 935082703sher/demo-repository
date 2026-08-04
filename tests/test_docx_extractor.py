"""Hardened local DOCX extraction tests using synthetic packages only."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.services.confidential_sources import OfflineExtractionPolicy
from app.services.docx_extractor import SafeDocxExtractor, UnsafeDocxError

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>"""
DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>FAQ</w:t></w:r></w:p>
    <w:p><w:r><w:t>Synthetic question?</w:t></w:r></w:p>
    <w:p><w:r><w:t>Synthetic answer.</w:t></w:r></w:p>
  </w:body>
</w:document>"""


def write_docx(
    path: Path,
    *,
    content_types: str = CONTENT_TYPES,
    root_rels: str = ROOT_RELS,
    document: str = DOCUMENT,
    extras: dict[str, str] | None = None,
) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", root_rels)
        package.writestr("word/document.xml", document)
        for name, content in (extras or {}).items():
            package.writestr(name, content)


def test_extracts_normalized_paragraphs_in_memory(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.docx"
    write_docx(source)

    result = SafeDocxExtractor().extract(source, policy=OfflineExtractionPolicy())

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "FAQ",
        "Synthetic question?",
        "Synthetic answer.",
    ]
    assert result.paragraphs[0].style == "Heading1"
    assert result.part_count == 3
    assert result.relationship_count == 1


def test_rejects_macro_enabled_content_type(tmp_path: Path) -> None:
    source = tmp_path / "macro.docx"
    write_docx(
        source,
        content_types=CONTENT_TYPES.replace(
            "wordprocessingml.document.main+xml", "wordprocessingml.document.macroEnabled.main+xml"
        ),
    )

    with pytest.raises(UnsafeDocxError, match="docx_macro_or_active_content_rejected"):
        SafeDocxExtractor().extract(source, policy=OfflineExtractionPolicy())


@pytest.mark.parametrize("part", ["word/vbaProject.bin", "word/embeddings/object1.bin"])
def test_rejects_macro_and_embedded_binary_parts(tmp_path: Path, part: str) -> None:
    source = tmp_path / "active.docx"
    write_docx(source, extras={part: "synthetic"})

    with pytest.raises(UnsafeDocxError, match="docx_package_unsafe"):
        SafeDocxExtractor().extract(source, policy=OfflineExtractionPolicy())


def test_rejects_external_non_hyperlink_relationship(tmp_path: Path) -> None:
    source = tmp_path / "external.docx"
    relationships = ROOT_RELS.replace(
        "</Relationships>",
        """<Relationship Id="rId2"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
        Target="https://example.invalid/tracker.png" TargetMode="External"/>
        </Relationships>""",
    )
    write_docx(source, root_rels=relationships)

    with pytest.raises(UnsafeDocxError, match="docx_external_relationship_rejected"):
        SafeDocxExtractor().extract(source, policy=OfflineExtractionPolicy())


def test_rejects_missing_and_malformed_document_xml(tmp_path: Path) -> None:
    missing = tmp_path / "missing.docx"
    with zipfile.ZipFile(missing, "w") as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", ROOT_RELS)
    malformed = tmp_path / "malformed.docx"
    write_docx(malformed, document="<not-closed>")

    with pytest.raises(UnsafeDocxError, match="docx_required_part_missing"):
        SafeDocxExtractor().extract(missing, policy=OfflineExtractionPolicy())
    with pytest.raises(UnsafeDocxError, match="docx_xml_malformed"):
        SafeDocxExtractor().extract(malformed, policy=OfflineExtractionPolicy())


def test_rejects_doctype_and_active_document_elements(tmp_path: Path) -> None:
    doctype = tmp_path / "doctype.docx"
    write_docx(doctype, document="<!DOCTYPE x><x/>")
    active = tmp_path / "active.docx"
    write_docx(
        active,
        document=DOCUMENT.replace("</w:body>", '<w:altChunk w:id="unsafe"/></w:body>'),
    )

    with pytest.raises(UnsafeDocxError, match="docx_xml_part_unsafe"):
        SafeDocxExtractor().extract(doctype, policy=OfflineExtractionPolicy())
    with pytest.raises(UnsafeDocxError, match="docx_embedded_or_active_content_rejected"):
        SafeDocxExtractor().extract(active, policy=OfflineExtractionPolicy())
