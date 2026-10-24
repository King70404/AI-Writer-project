"""Meter outgoing model requests and read the ledger; never calls a model itself."""

from collections.abc import Callable
from typing import Protocol

from aiwebnovel.ai_writing.application.models import GeneratedText, GenerationMessage
from aiwebnovel.ai_writing.errors import AIProviderTimeout
from aiwebnovel.core.logging import get_logger
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.model_gateway.models import ModelProfile
from aiwebnovel.usage.attribution import UsageAttribution, current_usage_attribution
from aiwebnovel.usage.models import AttemptStatus, UsageAttributionMissing, UsagePage
from aiwebnovel.usage.records import AttemptOutcome, AttemptStart

logger = get_logger("usage")


class UsageLedger(Protocol):
    def start(self, attempt: AttemptStart) -> str: ...

    def settle(self, attempt_id: str, outcome: AttemptOutcome) -> bool: ...

    def recover_interrupted(self) -> int: ...

    def page(
        self,
        project_id: str,
        chapter_id: str | None,
        task_id: str | None,
        offset: int,
        limit: int,
    ) -> UsagePage: ...


Send = Callable[[Callable[[ModelProfile], None]], GeneratedText]


def _error_code(error: BaseException) -> str:
    # Only a stable class name is kept; exception text may contain prose or secrets.
    return type(error).__name__ if isinstance(error, DomainError) else "AIProviderUnavailable"


class UsageLedgerService:
    def __init__(self, ledger: UsageLedger) -> None:
        self._ledger = ledger

    def metered(self, messages: tuple[GenerationMessage, ...], send: Send) -> GeneratedText:
        """Run ``send`` with a ``before_send`` hook that opens a ledger row.

        No row is written when a local check fails before the request; a row that was
        opened is settled exactly once with the provider's reported usage or unknown.
        """
        attribution: UsageAttribution | None = current_usage_attribution()
        if attribution is None:
            raise UsageAttributionMissing
        input_characters = sum(len(item.content) for item in messages)
        opened: list[str] = []

        def before_send(profile: ModelProfile) -> None:
            opened.append(
                self._ledger.start(
                    AttemptStart(
                        attribution, profile.id, profile.kind, profile.model, input_characters
                    )
                )
            )

        try:
            generated = send(before_send)
        except BaseException as error:
            if opened:
                status: AttemptStatus = (
                    "timeout" if isinstance(error, AIProviderTimeout) else "failed"
                )
                self._settle(opened[0], AttemptOutcome(status, _error_code(error), None, None))
            raise
        if opened:
            self._settle(
                opened[0],
                AttemptOutcome("completed", None, generated.usage, len(generated.text)),
            )
        return generated

    def _settle(self, attempt_id: str, outcome: AttemptOutcome) -> None:
        try:
            self._ledger.settle(attempt_id, outcome)
        except Exception:  # noqa: BLE001 - the row stays running and is marked interrupted.
            # A paid result must not be discarded because its ledger row failed to settle.
            logger.warning("usage settle failed attempt_id=%s", attempt_id)

    def recover_interrupted(self) -> int:
        return self._ledger.recover_interrupted()

    def project_usage(
        self,
        project_id: str,
        *,
        chapter_id: str | None = None,
        task_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> UsagePage:
        return self._ledger.page(project_id, chapter_id, task_id, offset, limit)
