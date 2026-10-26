"""Usage ledger read contracts.

Three quantities are kept strictly apart and never substitute for each other:

* ``input_characters`` / ``output_characters``: Unicode code points counted locally
  (``estimate_method`` ``local_characters_v1``). They are a local estimate basis, not
  tokens and not a bill.
* ``reported_*_tokens``: exactly what the provider's response reported; ``None``
  means the provider did not report it.
* ``usage_source == "unknown"``: no provider report exists (no usage field, a failed
  or timed-out request, or an interrupted process). Unknown is never counted as zero.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.usage.attribution import UsageOperation

AttemptStatus = Literal["running", "completed", "failed", "timeout", "interrupted"]
UsageSource = Literal["provider_reported", "unknown"]
ESTIMATE_METHOD: Literal["local_characters_v1"] = "local_characters_v1"
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class UsageAttributionMissing(DomainError):
    message = "A model request must name the operation it is recorded under."


class UsageLedgerUnavailable(DomainError):
    message = "The usage ledger could not record this request, so it was not sent."


class UsageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class UsageAttemptView(UsageModel):
    id: str
    chapter_id: str | None
    operation: UsageOperation
    task_id: str
    profile_id: str
    model_kind: Literal["local", "cloud"]
    model_name: str
    status: AttemptStatus
    error_code: str | None
    usage_source: UsageSource
    reported_input_tokens: int | None
    reported_output_tokens: int | None
    reported_total_tokens: int | None
    input_characters: int = Field(ge=0)
    output_characters: int | None
    started_at: str
    finished_at: str | None
    duration_ms: int | None


class UsageTotals(UsageModel):
    attempts: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    timeout: int = Field(ge=0)
    interrupted: int = Field(ge=0)
    running: int = Field(ge=0)
    reported_attempts: int = Field(ge=0)
    # Provider reported usage but omitted input or output tokens.
    incomplete_reports: int = Field(ge=0)
    unknown_attempts: int = Field(ge=0)
    reported_input_tokens: int = Field(ge=0)
    reported_output_tokens: int = Field(ge=0)
    reported_total_tokens: int = Field(ge=0)
    input_characters: int = Field(ge=0)
    output_characters: int = Field(ge=0)


class OperationUsage(UsageModel):
    operation: UsageOperation
    totals: UsageTotals


class ModelUsage(UsageModel):
    model_kind: Literal["local", "cloud"]
    model_name: str
    totals: UsageTotals


class UsagePage(UsageModel):
    project_id: str
    chapter_id: str | None
    task_id: str | None
    estimate_method: Literal["local_characters_v1"] = ESTIMATE_METHOD
    totals: UsageTotals
    by_operation: list[OperationUsage]
    by_model: list[ModelUsage]
    items: list[UsageAttemptView]
    total: int = Field(ge=0)
    next_offset: int | None
