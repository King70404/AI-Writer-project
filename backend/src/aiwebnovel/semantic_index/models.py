"""Semantic index contracts. The index is derived search data, never a source of facts.

Vectors come only from an explicitly confirmed, metered build with the author's own
embedding profile. Recall reads stored vectors and never calls a model; when the index
is missing or out of date it falls back to deterministic recall and says so.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_memory.models import SemanticRanking as SemanticRanking
from aiwebnovel.usage.budget import SendEstimate

EntryKind = Literal["fact", "chapter_chunk"]
CHUNK_CHARACTERS = 800
MAX_CHUNKS_PER_CHAPTER = 300
QUERY_CHUNKS = 10  # about the last 8,000 characters, the deterministic query window
BATCH_INPUTS = 32
BATCH_CHARACTERS = 24_000
MAX_ITEMS_PER_BUILD = 2_000

ProfileProblem = Literal["not_configured", "not_found", "not_embedding"]


class SemanticIndexInvalid(DomainError):
    message = "The semantic index request is invalid."


class SemanticIndexConflict(DomainError):
    message = "The index plan, price or settings changed. Review the new estimate first."


class SemanticIndexConfirmationRequired(DomainError):
    message = "Confirm the estimated tokens and cost (and cloud sending) before building."


class SemanticIndexNothingToDo(DomainError):
    message = "The semantic index is already up to date."


@dataclass(frozen=True, slots=True)
class EmbeddingModel:
    """Profile fields the index depends on; a change makes every vector stale."""

    id: str
    name: str
    kind: str
    base_url: str
    model: str
    purpose: str


@dataclass(frozen=True, slots=True)
class Entry:
    kind: EntryKind
    source_id: str
    chapter_id: str
    source_revision: str
    profile_id: str
    config_hash: str
    text_hash: str
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PlanItem:
    kind: EntryKind
    source_id: str
    chapter_id: str
    source_revision: str
    text: str
    text_hash: str


@dataclass(frozen=True, slots=True)
class Settings:
    version: int
    enabled: bool
    profile_id: str | None
    updated_at: str | None


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SettingsInput(Model):
    expected_version: int = Field(ge=0)
    enabled: bool
    profile_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class SettingsView(Model):
    version: int = Field(ge=0)
    enabled: bool
    profile_id: str | None
    updated_at: str | None


class ProfileView(Model):
    id: str
    name: str
    kind: Literal["local", "cloud"]
    model: str


class PlanView(Model):
    plan_version: str
    fact_items: int = Field(ge=0)
    chunk_items: int = Field(ge=0)
    requests: int = Field(ge=0)
    input_characters: int = Field(ge=0)
    # Items beyond the per-build cap wait for the next confirmed incremental build.
    deferred_items: int = Field(ge=0)
    obsolete_entries: int = Field(ge=0)


class IndexStatus(Model):
    project_id: str
    settings: SettingsView
    profile: ProfileView | None
    profile_problem: ProfileProblem | None
    facts_total: int = Field(ge=0)
    facts_indexed: int = Field(ge=0)
    chapters_total: int = Field(ge=0)
    chapters_indexed: int = Field(ge=0)
    stale_entries: int = Field(ge=0)
    up_to_date: bool
    plan: PlanView | None
    estimate: SendEstimate | None


class BuildInput(Model):
    plan_version: str = Field(min_length=64, max_length=64)
    confirm_estimate: bool = False
    cloud_consent: bool = False


class BuildResult(Model):
    build_id: str
    requests_sent: int = Field(ge=0)
    items_indexed: int = Field(ge=0)
    entries_removed: int = Field(ge=0)
    status: IndexStatus
