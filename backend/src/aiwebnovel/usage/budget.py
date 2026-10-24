"""Author-entered prices, budgets and conservative pre-send estimates (F06 / B2).

Plain, ORM-free contracts and arithmetic shared by the budget store and the HTTP
layer. Nothing here calls a model, presets a price or converts currencies.

Estimates are upper bounds, never bills:

* ``input_tokens_upper`` is the UTF-8 byte count of every message plus a fixed
  per-message overhead (``utf8_bytes_upper_v1``). Byte-level tokenizers emit at
  most one token per byte, so this bounds them; it is not the provider's count.
* ``output_tokens_upper`` is the model profile's configured ``max_output_tokens``,
  which is exactly the limit sent with the request.

Spending never counts an unknown result as zero: an attempt without a complete
provider report keeps its reserved upper bound ("pending"), and an attempt sent
without any price is "unpriced", which makes a monetary limit unprovable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.ai_writing.application.models import GenerationMessage
from aiwebnovel.domain.errors import DomainError

BudgetMode = Literal["off", "warn", "strict"]
BudgetDecision = Literal["allowed", "warning", "refused"]
BudgetReason = Literal[
    "PRICE_MISSING",
    "CURRENCY_MISMATCH",
    "UNPRICED_HISTORY",
    "TASK_LIMIT_EXCEEDED",
    "MONTHLY_LIMIT_EXCEEDED",
]
ESTIMATE_METHOD: Literal["utf8_bytes_upper_v1"] = "utf8_bytes_upper_v1"
MESSAGE_OVERHEAD_TOKENS = 8
REQUEST_OVERHEAD_TOKENS = 8
MICROS = 1_000_000
MAX_PRICE_MICROS = 100_000 * MICROS
MAX_BUDGET_MICROS = 100_000_000 * MICROS
CURRENCY = re.compile(r"[A-Z]{3}\Z")
AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?\Z")


class BudgetRefused(DomainError):
    message = "The conservative estimate would exceed the author's strict budget; nothing was sent."


class BudgetVersionConflict(DomainError):
    message = "The budget or price changed. Reload it before saving."


class BudgetInputInvalid(DomainError):
    message = "The budget or price input is invalid."


def parse_amount(value: object, *, maximum: int) -> int:
    """Parse a non-negative decimal string into integer micro-units, without rounding."""
    if type(value) is not str or not AMOUNT.fullmatch(value):
        raise BudgetInputInvalid
    micros = int(Decimal(value) * MICROS)
    if micros > maximum:
        raise BudgetInputInvalid
    return micros


def format_amount(micros: int) -> str:
    whole, fraction = divmod(micros, MICROS)
    text = f"{fraction:06d}".rstrip("0")
    return f"{whole}.{text.ljust(2, '0')}"


def parse_currency(value: object) -> str:
    if type(value) is not str or not CURRENCY.fullmatch(value):
        raise BudgetInputInvalid
    return value


def input_tokens_upper(messages: Iterable[GenerationMessage]) -> int:
    return REQUEST_OVERHEAD_TOKENS + sum(
        len(message.content.encode("utf-8")) + MESSAGE_OVERHEAD_TOKENS for message in messages
    )


def cost_micros(tokens: int, micros_per_million: int) -> int:
    # Round up: an estimate may overstate, never understate, the cost.
    return -(-tokens * micros_per_million // MICROS)


@dataclass(frozen=True, slots=True)
class Price:
    revision_id: str
    profile_id: str
    version: int
    currency: str
    input_micros_per_million: int
    output_micros_per_million: int
    created_at: str

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        return cost_micros(input_tokens, self.input_micros_per_million) + cost_micros(
            output_tokens, self.output_micros_per_million
        )


@dataclass(frozen=True, slots=True)
class Budget:
    project_id: str
    version: int
    mode: BudgetMode
    currency: str | None
    task_limit_micros: int | None
    monthly_limit_micros: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class Spend:
    """Spending in one currency; ``unpriced`` and ``other_currency`` cannot be summed."""

    attempts: int = 0
    settled_micros: int = 0
    pending_micros: int = 0
    unpriced_attempts: int = 0
    other_currency_attempts: int = 0

    @property
    def upper_micros(self) -> int:
        return self.settled_micros + self.pending_micros

    @property
    def bounded(self) -> bool:
        return self.unpriced_attempts == 0 and self.other_currency_attempts == 0


@dataclass(frozen=True, slots=True)
class AttemptCost:
    """One ledger row as the spend calculation sees it."""

    status: str
    reported_input_tokens: int | None
    reported_output_tokens: int | None
    reported_total_tokens: int | None
    reserved_micros: int | None
    currency: str | None
    input_micros_per_million: int | None
    output_micros_per_million: int | None


def settled_cost(row: AttemptCost) -> int | None:
    """The cost implied by a complete provider report, or ``None`` if unknown."""
    if (
        row.status != "completed"
        or row.input_micros_per_million is None
        or row.output_micros_per_million is None
    ):
        return None
    if row.reported_input_tokens is not None and row.reported_output_tokens is not None:
        return cost_micros(row.reported_input_tokens, row.input_micros_per_million) + cost_micros(
            row.reported_output_tokens, row.output_micros_per_million
        )
    if row.reported_total_tokens is not None:
        # Only a total was reported: price every token at the higher rate.
        return cost_micros(
            row.reported_total_tokens,
            max(row.input_micros_per_million, row.output_micros_per_million),
        )
    return None


def summarize(rows: Iterable[AttemptCost], currency: str | None) -> Spend:
    attempts = settled = pending = unpriced = other = 0
    for row in rows:
        attempts += 1
        if row.reserved_micros is None or row.currency is None:
            unpriced += 1
        elif currency is None or row.currency != currency:
            other += 1
        else:
            actual = settled_cost(row)
            if actual is None:
                pending += row.reserved_micros
            else:
                settled += actual
    return Spend(attempts, settled, pending, unpriced, other)


def evaluate(
    budget: Budget | None,
    price: Price | None,
    estimated_micros: int | None,
    task_spend: Spend,
    month_spend: Spend,
) -> tuple[BudgetDecision, tuple[BudgetReason, ...]]:
    if budget is None or budget.mode == "off":
        return "allowed", ()
    reasons: list[BudgetReason] = []
    cost: int | None = None
    if price is None:
        reasons.append("PRICE_MISSING")
    elif price.currency != budget.currency:
        reasons.append("CURRENCY_MISMATCH")
    else:
        cost = estimated_micros
    checks: tuple[tuple[int | None, Spend, BudgetReason], ...] = (
        (budget.task_limit_micros, task_spend, "TASK_LIMIT_EXCEEDED"),
        (budget.monthly_limit_micros, month_spend, "MONTHLY_LIMIT_EXCEEDED"),
    )
    for limit, spend, exceeded in checks:
        if limit is None:
            continue
        if not spend.bounded:
            if "UNPRICED_HISTORY" not in reasons:
                reasons.append("UNPRICED_HISTORY")
        elif cost is not None and spend.upper_micros + cost > limit:
            reasons.append(exceeded)
    if not reasons:
        return "allowed", ()
    return ("refused" if budget.mode == "strict" else "warning"), tuple(reasons)


@dataclass(frozen=True, slots=True)
class BudgetCheck:
    budget: Budget | None
    price: Price | None
    estimated_micros: int | None
    task: Spend
    month: Spend
    decision: BudgetDecision
    reasons: tuple[BudgetReason, ...]


@dataclass(frozen=True, slots=True)
class SendRequest:
    """What one outgoing request would cost at most, before it is sent."""

    project_id: str | None
    chapter_id: str | None
    task_id: str
    profile_id: str
    input_characters: int
    input_tokens_upper: int
    output_tokens_upper: int


class BudgetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PriceView(BudgetModel):
    profile_id: str
    version: int = Field(ge=1)
    currency: str
    input_per_million: str
    output_per_million: str
    created_at: str


class PriceState(BudgetModel):
    profile_id: str
    current: PriceView | None
    history: list[PriceView]


class SpendView(BudgetModel):
    currency: str | None
    attempts: int = Field(ge=0)
    settled: str
    pending: str
    upper: str
    unpriced_attempts: int = Field(ge=0)
    other_currency_attempts: int = Field(ge=0)


class BudgetView(BudgetModel):
    project_id: str
    version: int = Field(ge=0)
    mode: BudgetMode
    currency: str | None
    task_limit: str | None
    monthly_limit: str | None
    created_at: str | None
    month_start: str
    month: SpendView


class SendEstimate(BudgetModel):
    estimate_method: Literal["utf8_bytes_upper_v1"] = ESTIMATE_METHOD
    profile_id: str
    input_characters: int = Field(ge=0)
    input_tokens_upper: int = Field(ge=0)
    output_tokens_upper: int = Field(ge=0)
    price: PriceView | None
    estimated_cost_upper: str | None
    currency: str | None
    budget_mode: BudgetMode
    budget_currency: str | None
    task_limit: str | None
    monthly_limit: str | None
    task_spent_upper: str | None
    month_spent_upper: str | None
    unpriced_attempts: int = Field(ge=0)
    decision: BudgetDecision
    reasons: list[BudgetReason]


def price_view(price: Price) -> PriceView:
    return PriceView(
        profile_id=price.profile_id,
        version=price.version,
        currency=price.currency,
        input_per_million=format_amount(price.input_micros_per_million),
        output_per_million=format_amount(price.output_micros_per_million),
        created_at=price.created_at,
    )


def spend_view(spend: Spend, currency: str | None) -> SpendView:
    return SpendView(
        currency=currency,
        attempts=spend.attempts,
        settled=format_amount(spend.settled_micros),
        pending=format_amount(spend.pending_micros),
        upper=format_amount(spend.upper_micros),
        unpriced_attempts=spend.unpriced_attempts,
        other_currency_attempts=spend.other_currency_attempts,
    )


def optional_amount(micros: int | None) -> str | None:
    return None if micros is None else format_amount(micros)
