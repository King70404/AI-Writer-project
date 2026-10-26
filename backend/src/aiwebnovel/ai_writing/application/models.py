"""Immutable internal messages, candidates, and transparent context metadata."""

import re
from dataclasses import dataclass
from typing import Literal, Protocol

from aiwebnovel.ai_writing.errors import AIProviderInvalidResponse, InvalidAIInput
from aiwebnovel.novel_structure.errors import InvalidManuscriptContent
from aiwebnovel.novel_structure.values import ManuscriptContent

MAX_INSTRUCTION_CHARACTERS = 4_000
MAX_REWRITE_CHARACTERS = 50_000
MAX_GENERATED_CHARACTERS = 50_000
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")


def validate_text(value: object, *, limit: int, allow_empty: bool = False) -> str:
    if type(value) is not str or len(value) > limit:
        raise InvalidAIInput
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise InvalidAIInput
    try:
        normalized = str(ManuscriptContent(value))
    except InvalidManuscriptContent:
        raise InvalidAIInput from None
    if not allow_empty and not normalized.strip():
        raise InvalidAIInput
    return normalized


@dataclass(frozen=True, slots=True)
class GenerationMessage:
    role: Literal["system", "user"]
    content: str


MAX_REPORTED_TOKENS = 1_000_000_000


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Token counts exactly as the provider reported them; ``None`` means not reported."""

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


def _reported_count(value: object) -> int | None:
    if type(value) is int and 0 <= value <= MAX_REPORTED_TOKENS:
        return value
    return None


def parse_provider_usage(data: object) -> ProviderUsage | None:
    """Read an OpenAI-compatible ``usage`` object without guessing missing values.

    Malformed or absent usage is reported as ``None`` (unknown), never as zero, and
    never fails an otherwise valid response.
    """
    if type(data) is not dict:
        return None
    usage = data.get("usage")
    if type(usage) is not dict:
        return None
    input_tokens = _reported_count(usage.get("prompt_tokens", usage.get("input_tokens")))
    output_tokens = _reported_count(usage.get("completion_tokens", usage.get("output_tokens")))
    total_tokens = _reported_count(usage.get("total_tokens"))
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return ProviderUsage(input_tokens, output_tokens, total_tokens)


@dataclass(frozen=True, slots=True)
class GeneratedText:
    text: str
    model: str
    usage: ProviderUsage | None = None

    def __post_init__(self) -> None:
        try:
            normalized = validate_text(self.text, limit=MAX_GENERATED_CHARACTERS)
        except InvalidAIInput:
            raise AIProviderInvalidResponse from None
        if type(self.model) is not str or not MODEL_NAME.fullmatch(self.model):
            raise AIProviderInvalidResponse
        if self.usage is not None and type(self.usage) is not ProviderUsage:
            raise AIProviderInvalidResponse
        object.__setattr__(self, "text", normalized)


class TextGenerationProvider(Protocol):
    def generate(self, messages: tuple[GenerationMessage, ...]) -> GeneratedText: ...


@dataclass(frozen=True, slots=True)
class ContextSource:
    source: str
    references: tuple[tuple[str, str], ...]
    text: str
    reason: str
    omitted_reason: str | None
    truncated: bool


@dataclass(frozen=True, slots=True)
class ContextManifest:
    included_sources: tuple[str, ...]
    omitted_sources: tuple[str, ...]
    truncated: bool
    character_count: int
    sources: tuple[ContextSource, ...] = ()


@dataclass(frozen=True, slots=True)
class ChapterWritingContext:
    text: str
    manifest: ContextManifest


@dataclass(frozen=True, slots=True)
class GenerationCandidate:
    operation: Literal["continue", "rewrite"]
    text: str
    model: str
    context: ContextManifest
