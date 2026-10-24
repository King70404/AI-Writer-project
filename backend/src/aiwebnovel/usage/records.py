"""Plain, ORM-free records exchanged between the usage service and its ledger."""

from __future__ import annotations

from dataclasses import dataclass

from aiwebnovel.ai_writing.application.models import ProviderUsage
from aiwebnovel.usage.attribution import UsageAttribution
from aiwebnovel.usage.models import AttemptStatus

__all__ = ["AttemptOutcome", "AttemptStart"]


@dataclass(frozen=True, slots=True)
class AttemptStart:
    attribution: UsageAttribution
    profile_id: str
    model_kind: str
    model_name: str
    input_characters: int


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    status: AttemptStatus
    error_code: str | None
    usage: ProviderUsage | None
    output_characters: int | None
