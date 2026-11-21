"""Author prices, novel budgets and pre-send estimates; never calls a model."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from aiwebnovel.ai_writing.application.models import GenerationMessage
from aiwebnovel.model_gateway.models import PROFILE_ID, ModelProfile
from aiwebnovel.usage.budget import (
    MAX_BUDGET_MICROS,
    MAX_PRICE_MICROS,
    Budget,
    BudgetCheck,
    BudgetInputInvalid,
    BudgetMode,
    BudgetView,
    Price,
    PriceState,
    SendEstimate,
    SendRequest,
    Spend,
    embedding_tokens_upper,
    format_amount,
    input_tokens_upper,
    optional_amount,
    parse_amount,
    parse_currency,
    price_view,
    spend_view,
)


class BudgetStore(Protocol):
    def estimate(self, request: SendRequest) -> BudgetCheck: ...

    def price_history(self, profile_id: str) -> tuple[Price, ...]: ...

    def put_price(
        self,
        profile_id: str,
        expected_version: int,
        currency: str,
        input_micros: int,
        output_micros: int,
        cached_input_micros: int | None = None,
        cache_write_micros: int | None = None,
    ) -> None: ...

    def budget_state(self, project_id: str) -> tuple[Budget | None, datetime, Spend]: ...

    def put_budget(
        self,
        project_id: str,
        expected_version: int,
        mode: BudgetMode,
        currency: str | None,
        task_limit: int | None,
        monthly_limit: int | None,
    ) -> None: ...


def _version(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise BudgetInputInvalid
    return value


class UsageBudgetService:
    def __init__(self, store: BudgetStore, profile_reader: Callable[[str], ModelProfile]) -> None:
        self._store = store
        self._profiles = profile_reader

    def _profile(self, profile_id: str) -> ModelProfile:
        if type(profile_id) is not str or not PROFILE_ID.fullmatch(profile_id):
            raise BudgetInputInvalid
        return self._profiles(profile_id)

    def estimate(
        self,
        *,
        chapter_id: str | None,
        project_id: str | None,
        task_id: str,
        profile_id: str,
        messages: tuple[GenerationMessage, ...],
    ) -> SendEstimate:
        profile = self._profile(profile_id)
        request = SendRequest(
            project_id,
            chapter_id,
            task_id,
            profile.id,
            sum(len(item.content) for item in messages),
            input_tokens_upper(messages),
            profile.max_output_tokens,
        )
        return self._estimate(profile, request)

    def estimate_embedding(
        self,
        *,
        project_id: str,
        task_id: str,
        profile_id: str,
        batches: tuple[tuple[str, ...], ...],
    ) -> SendEstimate:
        """Aggregate upper bound for every embeddings request of one planned build.

        Each batch is one request; output tokens are zero. The whole build is checked
        as one task against the author's budget, before anything is sent.
        """
        profile = self._profile(profile_id)
        if profile.purpose != "embedding" or not batches:
            raise BudgetInputInvalid
        request = SendRequest(
            project_id,
            None,
            task_id,
            profile.id,
            sum(len(text) for batch in batches for text in batch),
            sum(embedding_tokens_upper(batch) for batch in batches),
            0,
        )
        return self._estimate(profile, request)

    def _estimate(self, profile: ModelProfile, request: SendRequest) -> SendEstimate:
        check = self._store.estimate(request)
        budget = check.budget
        return SendEstimate(
            profile_id=profile.id,
            input_characters=request.input_characters,
            input_tokens_upper=request.input_tokens_upper,
            output_tokens_upper=request.output_tokens_upper,
            price=None if check.price is None else price_view(check.price),
            estimated_cost_upper=optional_amount(check.estimated_micros),
            currency=None if check.price is None else check.price.currency,
            budget_mode="off" if budget is None else budget.mode,
            budget_currency=None if budget is None else budget.currency,
            task_limit=None if budget is None else optional_amount(budget.task_limit_micros),
            monthly_limit=None if budget is None else optional_amount(budget.monthly_limit_micros),
            task_spent_upper=format_amount(check.task.upper_micros) if budget else None,
            month_spent_upper=format_amount(check.month.upper_micros) if budget else None,
            unpriced_attempts=max(check.task.unpriced_attempts, check.month.unpriced_attempts),
            decision=check.decision,
            reasons=list(check.reasons),
        )

    def price_state(self, profile_id: str) -> PriceState:
        profile = self._profile(profile_id)
        history = self._store.price_history(profile.id)
        views = [price_view(price) for price in history]
        return PriceState(profile_id=profile.id, current=views[0] if views else None, history=views)

    def put_price(
        self,
        profile_id: str,
        *,
        expected_version: int,
        currency: str,
        input_per_million: str,
        output_per_million: str,
        cached_input_per_million: str | None = None,
        cache_write_per_million: str | None = None,
    ) -> PriceState:
        profile = self._profile(profile_id)
        self._store.put_price(
            profile.id,
            _version(expected_version),
            parse_currency(currency),
            parse_amount(input_per_million, maximum=MAX_PRICE_MICROS),
            parse_amount(output_per_million, maximum=MAX_PRICE_MICROS),
            None
            if cached_input_per_million is None
            else parse_amount(cached_input_per_million, maximum=MAX_PRICE_MICROS),
            None
            if cache_write_per_million is None
            else parse_amount(cache_write_per_million, maximum=MAX_PRICE_MICROS),
        )
        return self.price_state(profile.id)

    def budget_view(self, project_id: str) -> BudgetView:
        budget, start, month = self._store.budget_state(project_id)
        return BudgetView(
            project_id=project_id,
            version=0 if budget is None else budget.version,
            mode="off" if budget is None else budget.mode,
            currency=None if budget is None else budget.currency,
            task_limit=None if budget is None else optional_amount(budget.task_limit_micros),
            monthly_limit=None if budget is None else optional_amount(budget.monthly_limit_micros),
            created_at=None if budget is None else budget.created_at,
            month_start=start.astimezone(UTC).isoformat(),
            month=spend_view(month, None if budget is None else budget.currency),
        )

    def put_budget(
        self,
        project_id: str,
        *,
        expected_version: int,
        mode: BudgetMode,
        currency: str | None,
        task_limit: str | None,
        monthly_limit: str | None,
    ) -> BudgetView:
        if mode not in ("off", "warn", "strict"):
            raise BudgetInputInvalid
        task = None if task_limit is None else parse_amount(task_limit, maximum=MAX_BUDGET_MICROS)
        month = (
            None
            if monthly_limit is None
            else parse_amount(monthly_limit, maximum=MAX_BUDGET_MICROS)
        )
        code = None if currency is None else parse_currency(currency)
        if mode != "off" and (code is None or (task is None and month is None)):
            raise BudgetInputInvalid
        self._store.put_budget(project_id, _version(expected_version), mode, code, task, month)
        return self.budget_view(project_id)
