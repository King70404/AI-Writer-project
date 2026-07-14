"""Validate independent backend statement and branch coverage thresholds."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

STATEMENT_THRESHOLD = 80.0
BRANCH_THRESHOLD = 75.0


class CoverageReportError(ValueError):
    """Raised when a coverage report cannot prove the required measurements."""


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise CoverageReportError(f"{field} must be an object")
    return value


def _number(mapping: Mapping[str, object], field: str) -> float:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoverageReportError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise CoverageReportError(f"{field} must be a finite non-negative number")
    return result


def read_coverage_percentages(report_path: Path) -> tuple[float, float]:
    """Read pure statement and branch percentages from coverage.py totals."""
    try:
        with report_path.open("r", encoding="utf-8") as report_file:
            payload: object = json.load(report_file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoverageReportError("coverage JSON could not be read") from exc

    root = _mapping(payload, "report")
    totals = _mapping(root.get("totals"), "totals")
    statement_count = _number(totals, "num_statements")
    covered_statements = _number(totals, "covered_lines")
    branch_count = _number(totals, "num_branches")
    covered_branches = _number(totals, "covered_branches")

    if statement_count <= 0:
        raise CoverageReportError("statement measurement is empty")
    if branch_count <= 0:
        raise CoverageReportError("branch measurement is empty")
    if covered_statements > statement_count or covered_branches > branch_count:
        raise CoverageReportError("covered counts exceed measured counts")

    return (
        100.0 * covered_statements / statement_count,
        100.0 * covered_branches / branch_count,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check backend statement and branch coverage independently."
    )
    parser.add_argument("report", type=Path, help="coverage.py JSON report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        statement_percent, branch_percent = read_coverage_percentages(args.report)
    except CoverageReportError as exc:
        print(f"[coverage] invalid report: {exc}")
        return 2

    print(f"[coverage] backend: statements={statement_percent:.2f}% branches={branch_percent:.2f}%")

    failures: list[str] = []
    if statement_percent < STATEMENT_THRESHOLD:
        failures.append(
            "statement coverage below threshold: "
            f"{statement_percent:.2f}% < {STATEMENT_THRESHOLD:.2f}%"
        )
    if branch_percent < BRANCH_THRESHOLD:
        failures.append(
            f"branch coverage below threshold: {branch_percent:.2f}% < {BRANCH_THRESHOLD:.2f}%"
        )

    for failure in failures:
        print(f"[coverage] failed: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
