"""Local CLI for content-free source hash manifests and verification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.domain.governance import SourceManifest
from app.services.confidential_sources import ConfidentialSourceError, sha256_file, verify_manifest


def load_manifest(path: Path) -> SourceManifest:
    """Load strict manifest metadata without reading any listed source content."""
    return SourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def create_local_pdf_manifest(*, source_root: Path, output: Path) -> int:
    """Write a mode-600 local PDF filename/hash inventory outside the repository."""
    root = source_root.resolve(strict=True)
    output_parent = output.parent.resolve(strict=True)
    if output_parent != root or output.exists() or output.is_symlink():
        raise ConfidentialSourceError("local_manifest_output_must_be_new_and_in_source_root")
    entries: list[dict[str, str]] = []
    for source in sorted(root.iterdir(), key=lambda item: item.name):
        if source.suffix.casefold() != ".pdf":
            continue
        if source.is_symlink() or not source.is_file():
            raise ConfidentialSourceError("pdf_source_not_regular_file")
        entries.append({"filename": source.name, "sha256": sha256_file(source)})
    payload = json.dumps(
        {"manifest_version": 1, "classification": "local_confidential", "files": entries},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(payload)
        target.write("\n")
    return len(entries)


def main() -> int:
    """Create a local PDF inventory or verify a strict reviewed source manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create-pdf")
    create_parser.add_argument("--source-root", required=True, type=Path)
    create_parser.add_argument("--output", required=True, type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--source-root", required=True, type=Path)
    verify_parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create-pdf":
            count = create_local_pdf_manifest(source_root=args.source_root, output=args.output)
            print(json.dumps({"created": True, "pdf_count": count}))
        else:
            manifest = load_manifest(args.manifest)
            results = verify_manifest(manifest, source_root=args.source_root)
            print(
                json.dumps(
                    {
                        "verified": True,
                        "source_ids": [result.source_id for result in results],
                    }
                )
            )
    except (OSError, ValidationError, ConfidentialSourceError, json.JSONDecodeError) as exc:
        print(json.dumps({"verified": False, "error_type": type(exc).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
