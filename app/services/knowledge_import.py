"""Validation-only import boundary for approved RTMC knowledge files."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import ValidationError

from app.services.knowledge import KnowledgeService


@dataclass(frozen=True, slots=True)
class KnowledgeImportReport:
    """Safe validation report without document content."""

    total: int
    eligible_ids: list[str]
    rejected_ids: list[str]


def validate_knowledge_file(path: Path) -> KnowledgeImportReport:
    """Parse the full file and reject records that cannot be safely retrieved."""
    service = KnowledgeService.from_json(path)
    eligible, rejected = service.validation_results()
    return KnowledgeImportReport(
        total=len(eligible) + len(rejected),
        eligible_ids=eligible,
        rejected_ids=rejected,
    )


def main() -> int:
    """Validate one candidate file without mutating application knowledge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        report = validate_knowledge_file(args.path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(json.dumps({"valid": False, "error_type": type(exc).__name__}))
        return 1
    print(json.dumps({"valid": not report.rejected_ids, **asdict(report)}, indent=2))
    return 0 if not report.rejected_ids else 2


if __name__ == "__main__":
    raise SystemExit(main())
