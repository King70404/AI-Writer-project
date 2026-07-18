"""Typed diagnostic status, aggregation, and exit-code tests."""

from typing import cast

import pytest

from aiwebnovel.diagnostics.models import (
    CheckStatus,
    DiagnosticCheck,
    DiagnosticExitCode,
    DiagnosticMode,
    DiagnosticReport,
    OverallStatus,
    detail_items,
)

pytestmark = pytest.mark.unit


def _check(
    status: CheckStatus,
    *,
    check_id: str = "ENV-001",
    required: bool = True,
) -> DiagnosticCheck:
    return DiagnosticCheck(
        check_id=check_id,
        name="Controlled check",
        status=status,
        summary="Controlled result.",
        details=detail_items(alpha=1, beta=True),
        remediation="Controlled remediation.",
        required=required,
        duration_ms=0,
    )


@pytest.mark.parametrize(
    ("checks", "expected_status", "expected_exit"),
    (
        ((_check(CheckStatus.PASS),), OverallStatus.READY, DiagnosticExitCode.READY),
        (
            (_check(CheckStatus.WARNING),),
            OverallStatus.READY_WITH_WARNINGS,
            DiagnosticExitCode.READY_WITH_WARNINGS,
        ),
        (
            (_check(CheckStatus.FAIL),),
            OverallStatus.NOT_READY,
            DiagnosticExitCode.NOT_READY,
        ),
        (
            (_check(CheckStatus.SKIPPED),),
            OverallStatus.NOT_READY,
            DiagnosticExitCode.NOT_READY,
        ),
        (
            (_check(CheckStatus.SKIPPED, required=False),),
            OverallStatus.READY,
            DiagnosticExitCode.READY,
        ),
    ),
)
def test_report_aggregation_and_exit_codes(
    checks: tuple[DiagnosticCheck, ...],
    expected_status: OverallStatus,
    expected_exit: DiagnosticExitCode,
) -> None:
    report = DiagnosticReport(mode=DiagnosticMode.DEVELOPMENT, checks=checks)

    assert report.overall_status is expected_status
    assert report.exit_code is expected_exit
    assert report.to_dict()["overall_status"] == expected_status.value


def test_report_preserves_check_order_and_stable_details() -> None:
    report = DiagnosticReport(
        mode=DiagnosticMode.M0,
        checks=(
            _check(CheckStatus.PASS, check_id="ENV-001"),
            _check(CheckStatus.WARNING, check_id="ENV-002", required=False),
        ),
    )
    payload = report.to_dict()
    checks = cast(list[dict[str, object]], payload["checks"])

    assert [item["check_id"] for item in checks] == ["ENV-001", "ENV-002"]
    assert checks[0]["details"] == {"alpha": 1, "beta": True}


def test_duplicate_or_invalid_check_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="invalid"):
        _check(CheckStatus.PASS, check_id="BAD-001")

    duplicate = _check(CheckStatus.PASS)
    with pytest.raises(ValueError, match="unique"):
        DiagnosticReport(
            mode=DiagnosticMode.DEVELOPMENT,
            checks=(duplicate, duplicate),
        )


def test_invalid_duration_and_unsorted_details_are_rejected() -> None:
    with pytest.raises(ValueError, match="duration"):
        DiagnosticCheck(
            check_id="ENV-001",
            name="Controlled",
            status=CheckStatus.PASS,
            summary="Controlled.",
            details=(),
            remediation="",
            required=True,
            duration_ms=-1,
        )
    with pytest.raises(ValueError, match="details"):
        DiagnosticCheck(
            check_id="ENV-001",
            name="Controlled",
            status=CheckStatus.PASS,
            summary="Controlled.",
            details=(("z", 1), ("a", 2)),
            remediation="",
            required=True,
            duration_ms=0,
        )
