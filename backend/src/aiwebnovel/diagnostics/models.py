"""Stable models and aggregation rules for environment diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

type DetailValue = str | int | bool | None
type DetailItems = tuple[tuple[str, DetailValue], ...]

_CHECK_ID = re.compile(r"^ENV-\d{3}$")


class DiagnosticMode(StrEnum):
    """Supported readiness policies."""

    DEVELOPMENT = "development"
    INTEGRATED = "integrated"
    M0 = "m0"


class CheckStatus(StrEnum):
    """One diagnostic check outcome."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    SKIPPED = "skipped"


class OverallStatus(StrEnum):
    """Aggregated environment readiness."""

    READY = "ready"
    READY_WITH_WARNINGS = "ready_with_warnings"
    NOT_READY = "not_ready"


class DiagnosticExitCode(IntEnum):
    """Stable command exit codes."""

    READY = 0
    READY_WITH_WARNINGS = 1
    NOT_READY = 2
    INVOCATION_ERROR = 3


def detail_items(**values: DetailValue) -> DetailItems:
    """Return deterministically ordered detail entries."""
    return tuple(sorted(values.items()))


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Untimed result returned by one check implementation."""

    status: CheckStatus
    summary: str
    details: DetailItems = ()
    remediation: str = ""
    required: bool = True


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    """Complete, serializable result for one stable check ID."""

    check_id: str
    name: str
    status: CheckStatus
    summary: str
    details: DetailItems
    remediation: str
    required: bool
    duration_ms: int

    def __post_init__(self) -> None:
        if _CHECK_ID.fullmatch(self.check_id) is None:
            raise ValueError("diagnostic check ID is invalid")
        if not self.name.strip() or not self.summary.strip():
            raise ValueError("diagnostic check text must not be blank")
        if self.duration_ms < 0:
            raise ValueError("diagnostic duration must not be negative")
        detail_keys = [key for key, _value in self.details]
        if detail_keys != sorted(detail_keys) or len(detail_keys) != len(set(detail_keys)):
            raise ValueError("diagnostic details must have unique sorted keys")

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible mapping."""
        return {
            "check_id": self.check_id,
            "name": self.name,
            "status": self.status.value,
            "summary": self.summary,
            "details": dict(self.details),
            "remediation": self.remediation,
            "required": self.required,
            "duration_ms": self.duration_ms,
        }


def aggregate_status(checks: tuple[DiagnosticCheck, ...]) -> OverallStatus:
    """Aggregate outcomes, treating a skipped required check as fail-closed."""
    if any(
        check.required and check.status in {CheckStatus.FAIL, CheckStatus.SKIPPED}
        for check in checks
    ):
        return OverallStatus.NOT_READY
    if any(check.status is CheckStatus.WARNING for check in checks):
        return OverallStatus.READY_WITH_WARNINGS
    return OverallStatus.READY


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """One complete diagnostic run."""

    mode: DiagnosticMode
    checks: tuple[DiagnosticCheck, ...]
    overall_status: OverallStatus = field(init=False)
    schema_version: str = "1"

    def __post_init__(self) -> None:
        check_ids = [check.check_id for check in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("diagnostic check IDs must be unique")
        object.__setattr__(self, "overall_status", aggregate_status(self.checks))

    @property
    def exit_code(self) -> DiagnosticExitCode:
        """Return the stable process code for the aggregate state."""
        return {
            OverallStatus.READY: DiagnosticExitCode.READY,
            OverallStatus.READY_WITH_WARNINGS: DiagnosticExitCode.READY_WITH_WARNINGS,
            OverallStatus.NOT_READY: DiagnosticExitCode.NOT_READY,
        }[self.overall_status]

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible report mapping."""
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "overall_status": self.overall_status.value,
            "checks": [check.to_dict() for check in self.checks],
        }
