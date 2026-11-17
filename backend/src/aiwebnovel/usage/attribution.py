"""Explicit business attribution for the next model request on this call stack.

Every business call site wraps its provider call in :func:`usage_attribution`. The
composed provider refuses to send a request without one, so no generation, reference
analysis or story review can bypass the usage ledger.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

UsageOperation = Literal["generation", "reference_analysis", "story_review", "connection_check"]


@dataclass(frozen=True, slots=True)
class UsageAttribution:
    operation: UsageOperation
    task_id: str
    project_id: str | None = None
    chapter_id: str | None = None


_CURRENT: ContextVar[UsageAttribution | None] = ContextVar("usage_attribution", default=None)


@contextmanager
def usage_attribution(
    operation: UsageOperation,
    task_id: str,
    *,
    project_id: str | None = None,
    chapter_id: str | None = None,
) -> Iterator[UsageAttribution]:
    attribution = UsageAttribution(operation, task_id, project_id, chapter_id)
    token = _CURRENT.set(attribution)
    try:
        yield attribution
    finally:
        _CURRENT.reset(token)


def current_usage_attribution() -> UsageAttribution | None:
    return _CURRENT.get()
