"""Build gate for likely PII in committed JSON knowledge and evaluation fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.pii import DerivedFixturePIIError, validate_derived_fixture


def scan_json_path(path: Path) -> list[str]:
    """Return failing paths without printing sensitive values."""
    candidates = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    failures: list[str] = []
    for candidate in candidates:
        try:
            value: Any = json.loads(candidate.read_text(encoding="utf-8"))
            validate_derived_fixture(value)
        except (OSError, json.JSONDecodeError, DerivedFixturePIIError):
            failures.append(candidate.as_posix())
    return failures


def main() -> int:
    """Scan selected committed fixture roots and fail without echoing their content."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failures = [failure for path in args.paths for failure in scan_json_path(path)]
    print(json.dumps({"passed": not failures, "failed_paths": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
