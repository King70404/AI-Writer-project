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


@dataclass(frozen=True, slots=True)
class GeneratedText:
    text: str
    model: str

    def __post_init__(self) -> None:
        try:
            normalized = validate_text(self.text, limit=MAX_GENERATED_CHARACTERS)
        except InvalidAIInput:
            raise AIProviderInvalidResponse from None
        if type(self.model) is not str or not MODEL_NAME.fullmatch(self.model):
            raise AIProviderInvalidResponse
        object.__setattr__(self, "text", normalized)


class TextGenerationProvider(Protocol):
    def generate(self, messages: tuple[GenerationMessage, ...]) -> GeneratedText: ...


@dataclass(frozen=True, slots=True)
class ContextManifest:
    included_sources: tuple[str, ...]
    omitted_sources: tuple[str, ...]
    truncated: bool
    character_count: int


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
